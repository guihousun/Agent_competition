from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path
from typing import Any

from source.runtime.env_config import ModelConfig, env_bool, env_int, load_dotenv
from source.runtime.agent_context import AgentContext
from source.runtime.openai_chat_client import ChatCompletionClient, first_message
from source.runtime.tracing import get_active_trace
from source.runtime.context_compressor import should_compress, compress_messages, estimate_messages_tokens


def tool_output_max_chars() -> int:
    return env_int("AGENT_DEMO_TOOL_OUTPUT_MAX_CHARS", 65_536)


def max_agent_iterations() -> int:
    return max(1, env_int("AGENT_DEMO_MAX_ITER", 10))


def _tool_output_for_history(content: str) -> str:
    return content[:tool_output_max_chars()]


PARALLEL_SAFE_TOOLS = frozenset(
    {
        "archive_inspect",
        "csv_aggregate",
        "csv_read",
        "dataset_bundle_read",
        "date_compute",
        "document_search",
        "file_list",
        "image_read",
        "mock_order_lookup",
        "mock_policy_check",
        "skill_load",
        "skill_read_resource",
        "sql_query",
        "text_read_file",
    }
)


class SoftDeadlineExceeded(Exception):
    """Raised when the question should stop gathering evidence and answer now."""


SYSTEM_PROMPT = """
你是 Agent 大赛参赛 Agent，在无人值守环境独立解题。

【原则】
- 不得询问用户或等待确认；用题面、附件和 capabilities 自主完成。
- question 的 tools/skills/sub_agents 只是提示，不是权限限制。
- 文件内容不会自动进入上下文；需要证据时读取附件，目录先 file_list。
- 事实、日期、计算、数据库、图片、接口响应以工具和资料为准。

【工具策略】
- 多个独立只读/纯计算工具同一轮批量调用；存在依赖、网络、状态变更、解压、Skill、子 Agent 时串行。
- 日期/工作日题统一调用 date_compute；多条日期题一次调用 date_compute(items=[...])，单条日期保留完整原句 expression。
- 多张图片一次调用 image_read(items=[...])；读到图片后直接基于已注入图像回答，不要同参重复读取。
- 压缩包先用 archive_inspect 一次解压并列出文件与文本预览；preview 不足或题目要求完整证据时，用 extracted_path 继续读取全文。
- 多表、多文档、多证据目录审计先用 dataset_bundle_read 一次读取；需计算时让 code_execute 读取 bundle_path，不要把全量数据复制进代码。
- 大表/数据库用合适工具或 Skill；Skill 先 skill_load 再按说明 skill_run。
- 编程规范/文档问答优先用 document_search 在附件 docx/md/txt 中检索相关条款，不要为此调用 subagent。
- 多源故障证据用 evidence_chain_analyze；顺序接口用例先规划，再 api_test_execute。
- Java 个税计算器题可 skill_load java_tax_solver，但主 Agent 自己读源码、修复、运行和计算。
- 不重复同参调用；失败后修正参数或换可验证方案。

【关键示例】
多条日期：text_read_file 后一次 date_compute(items)，按原顺序汇总。获取 token → 写接口 → 查询结果这类任务必须串行。

【输出】
- 主 Agent 负责正确性；提交前核对约束、证据、顺序、数量、精度和格式。
- 最终只输出答案正文；除非题目要求，不输出解释、Markdown、<think>、过程标签或 {"answer": ...} 包装。
- JSON 必须合法；字段、分隔符、排序、去重和精度严格按题面。
""".strip()


class ContestantAgent:
    """Contestant-editable main agent entrypoint."""

    async def solve(self, *, question: dict[str, Any], context: AgentContext) -> str:
        load_dotenv()
        if not env_bool("AGENT_DEMO_USE_LLM", True):
            raise RuntimeError("AGENT_DEMO_USE_LLM is disabled; configure a model gateway or implement ContestantAgent.solve().")

        # 参赛者主要改这里：
        # - question 是赛方运行器传入的公开题面对象，只包含 id/question/files 等可见字段。
        # - question["files"] 是本题允许读取的文件或目录列表，文件内容不会自动进入上下文。
        # - question 中的 tools/skills/sub_agents 是赛题提示，不会限制默认开放的能力。
        # - context 提供当前 solution 自动发现到的 MCP tools、skills、sub-agents 以及 call_tool(...) 调用入口。
        # - available_tools / available_skills / available_sub_agents 会一起传给模型，供主 Agent 自己决定是否调用。
        user_prompt = json.dumps(
            {
                "question": question,
                "capabilities": {
                    "tools": context.available_tools,
                    "skills": context.available_skills,
                    "sub_agents": context.available_agents,
                },
                **self._task_guidance(question),
                "instruction": "Treat question capability fields as hints, not restrictions. Solve autonomously and return only the final answer.",
            },
            ensure_ascii=False,
            indent=2,
        )

        return await self._run_model_loop(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            context=context,
        )

    def _task_guidance(self, question: dict[str, Any]) -> dict[str, str]:
        question_text = json.dumps(question, ensure_ascii=False)
        files = [str(path) for path in (question.get("files") or [])]
        guidance_parts: list[str] = []

        if "审计" in question_text and any(
            not Path(file_name).suffix for file_name in files
        ):
            guidance_parts.append(
                "这是多文件审计任务。先对题目声明的目录调用 dataset_bundle_read，一次获得表格、规则和证据；"
                "如果需要程序计算，让 code_execute 从返回的 bundle_path 读取 JSON。"
                "不要逐个 text_read_file，也不要把全量表格和证据复制进代码。"
            )

        has_java_source = any(
            Path(file_name).name.lower().startswith("javasource_")
            and Path(file_name).suffix.lower() == ".java"
            for file_name in files
        )
        if has_java_source and "所得税" in question_text:
            skill_path = Path(__file__).resolve().parent / "skills" / "java_tax_solver" / "SKILL.md"
            try:
                guidance = skill_path.read_text(encoding="utf-8")
            except OSError:
                guidance = (
                    "java_tax_solver: 修复 Java 源码，动态读取源码中的税率表、起征点和题面工资用例；"
                    "不要硬编码官方样例答案；参考 scripts/tax_repair_example.py 的模式，用 code_execute 的 python 模式验证。"
                )
            guidance_parts.append(guidance[:8000])

        if not guidance_parts:
            return {}
        return {
            "task_guidance": "\n\n".join(guidance_parts),
        }

    async def _run_model_loop(self, *, system_prompt: str, user_prompt: str, context: AgentContext) -> str:
        if not env_bool("AGENT_DEMO_NATIVE_TOOLS", True):
            return await self._run_json_tool_loop(system_prompt=system_prompt, user_prompt=user_prompt, context=context)

        try:
            return await self._run_native_tool_loop(system_prompt=system_prompt, user_prompt=user_prompt, context=context)
        except Exception as exc:
            if (
                env_bool("AGENT_DEMO_JSON_TOOL_FALLBACK", True)
                and self._is_native_tools_unsupported_error(exc)
            ):
                try:
                    return await self._run_json_tool_loop(system_prompt=system_prompt, user_prompt=user_prompt, context=context)
                except Exception:
                    pass
            raise

    def _is_native_tools_unsupported_error(self, exc: Exception) -> bool:
        text = str(exc).lower()
        tool_markers = (
            "tools",
            "tool_choice",
            "function calling",
            "function_call",
        )
        unsupported_markers = (
            "unsupported",
            "not supported",
            "unknown parameter",
            "unrecognized",
            "invalid parameter",
        )
        return any(marker in text for marker in tool_markers) and any(
            marker in text for marker in unsupported_markers
        )

    async def _run_native_tool_loop(self, *, system_prompt: str, user_prompt: str, context: AgentContext) -> str:
        config = ModelConfig.from_env()
        client = ChatCompletionClient(config)
        tools = await context.mcp.list_openai_tools(
            allowed_tools=context.allowed_tools,
            allowed_agents=context.allowed_agents,
        )
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        max_iter = max_agent_iterations()
        for step in range(1, max_iter + 1):
            # Context compression: when approaching 256k limit, compress older messages
            if should_compress(messages, limit=200_000):
                messages[:] = await compress_messages(
                    messages, keep_recent=10, target_tokens=150_000,
                    client=client,
                )

            try:
                completion = await self._create_before_soft_deadline(
                    client,
                    context,
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                )
            except SoftDeadlineExceeded:
                return await self._final_answer_now(messages=messages, client=client)
            message = first_message(completion)
            tool_calls = self._tool_calls_from_message(message)
            content = str(message.get("content") or "")

            messages.append(self._assistant_message_for_history(message))
            if not tool_calls:
                if content.strip():
                    candidate = self._clean_final_answer(content)
                    # 强制流水线：候选答案 → answer_checker → 决定下一步
                    return await self._verify_and_fix(
                        candidate=candidate,
                        messages=messages,
                        client=client,
                        tools=tools,
                        context=context,
                    )
                messages.append({"role": "user", "content": "请输出最终答案文本。"})
                continue

            prepared_calls = []
            for tool_call in tool_calls:
                tool_name = self._tool_call_name(tool_call)
                args_text = self._tool_call_arguments(tool_call)
                try:
                    tool_args = json.loads(args_text)
                except json.JSONDecodeError:
                    tool_args = {}
                prepared_calls.append((tool_name, tool_args))

            try:
                tool_results = await self._execute_before_soft_deadline(
                    context,
                    prepared_calls,
                )
            except SoftDeadlineExceeded:
                for tool_call, (tool_name, _) in zip(tool_calls, prepared_calls):
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.get("id", ""),
                            "name": tool_name,
                            "content": "已到达时间截止点，本次工具调用未完成。",
                        }
                    )
                return await self._final_answer_now(messages=messages, client=client)
            for tool_call, (tool_name, _), tool_result in zip(
                tool_calls,
                prepared_calls,
                tool_results,
            ):

                # Check if this is an image result — inject as multimodal content
                image_injected = False
                if tool_name == "image_read":
                    try:
                        img_data = json.loads(tool_result)
                        image_items = []
                        if img_data.get("__images__") and isinstance(img_data.get("images"), list):
                            image_items = [
                                item for item in img_data["images"]
                                if isinstance(item, dict) and item.get("__image__")
                            ]
                        elif img_data.get("__image__"):
                            image_items = [img_data]

                        if image_items:
                            # Add tool result with summary
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.get("id", ""),
                                "name": tool_name,
                                "content": "已读取图片: " + ", ".join(
                                    str(item.get("path", "")) for item in image_items
                                ),
                            })
                            # Inject image as multimodal user message
                            multimodal_content: list[dict[str, Any]] = []
                            for index, item in enumerate(image_items, start=1):
                                image_path = str(item.get("path", ""))
                                image_label = f"图片 {index}: {Path(image_path).name or image_path}"
                                image_question = item.get("question") or "请描述图片内容。"
                                multimodal_content.append({
                                    "type": "text",
                                    "text": (
                                        f"{image_label}\n"
                                        f"{image_question}\n"
                                        "回答时保持这张图片与上述文件名的对应关系；不要再次读取同一批图片。"
                                    ),
                                })
                                multimodal_content.append({
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:{item['mime_type']};base64,{item['base64']}"
                                    },
                                })
                            messages.append({
                                "role": "user",
                                "content": multimodal_content,
                            })
                            image_injected = True
                    except (json.JSONDecodeError, KeyError):
                        pass

                if not image_injected:
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.get("id", ""),
                            "name": tool_name,
                            "content": _tool_output_for_history(tool_result),
                        }
                    )

        messages.append({"role": "user", "content": "请停止调用工具，直接输出最终答案文本。"})
        completion = await client.create(messages=messages, tools=[], tool_choice="none")
        candidate = self._clean_final_answer(str(first_message(completion).get("content") or ""))
        return await self._verify_and_fix(
            candidate=candidate, messages=messages, client=client, tools=tools, context=context,
        )

    async def _run_json_tool_loop(self, *, system_prompt: str, user_prompt: str, context: AgentContext) -> str:
        """Prompt-level JSON tool loop for gateways that reject native tools."""

        config = ModelConfig.from_env()
        client = ChatCompletionClient(config)
        tools = await context.mcp.list_openai_tools(
            allowed_tools=context.allowed_tools,
            allowed_agents=context.allowed_agents,
        )
        tool_specs = [
            {
                "name": tool["function"]["name"],
                "description": tool["function"].get("description", ""),
                "parameters": tool["function"].get("parameters", {}),
            }
            for tool in tools
        ]
        json_tool_prompt = (
            system_prompt
            + "\n\n当前模型网关可能不支持原生 tools 字段。"
            + "\n需要工具时，只输出 JSON，且第一个字符必须是 {，不要输出 markdown 代码块或思考过程："
            + '{"tool_calls":[{"name":"工具名","arguments":{}}]}'
            + "\n彼此独立的只读工具应放入同一个 tool_calls 数组；存在依赖或副作用时按顺序分轮请求。"
            + "\n任务完成时，直接输出最终答案文本；不要包成结果对象。"
        )

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": json_tool_prompt},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "prompt": user_prompt,
                        "available_tools": tool_specs,
                        "instruction": "如果需要工具，只输出 tool_calls JSON；如果不需要工具，直接输出最终答案文本。",
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            },
        ]

        max_iter = max_agent_iterations()
        for step in range(1, max_iter + 1):
            try:
                completion = await self._create_before_soft_deadline(
                    client,
                    context,
                    messages=messages,
                    tools=[],
                    tool_choice="none",
                )
            except SoftDeadlineExceeded:
                return await self._final_answer_now(messages=messages, client=client)
            content = str(first_message(completion).get("content") or "").strip()

            parsed = self._parse_json_object(content)
            tool_calls = self._json_prompt_tool_calls(parsed) if parsed else None
            if not tool_calls:
                if content:
                    candidate = self._clean_final_answer(content)
                    return await self._verify_and_fix(
                        candidate=candidate,
                        messages=messages,
                        client=client,
                        tools=tools,
                        context=context,
                    )
                messages.append({"role": "user", "content": "请输出最终答案文本，或输出 tool_calls JSON。"})
                continue

            prepared_calls = []
            prepared_indexes = []
            for call_index, tool_call in enumerate(tool_calls):
                if not isinstance(tool_call, dict):
                    continue
                tool_name = str(tool_call.get("name") or tool_call.get("tool") or "")
                tool_args = tool_call.get("arguments")
                if tool_args is None:
                    tool_args = {
                        key: value
                        for key, value in tool_call.items()
                        if key not in {"name", "tool"}
                    }
                if not isinstance(tool_args, dict):
                    tool_args = {}
                prepared_indexes.append(call_index)
                prepared_calls.append((tool_name, tool_args))

            try:
                executed_results = await self._execute_before_soft_deadline(
                    context,
                    prepared_calls,
                )
            except SoftDeadlineExceeded:
                return await self._final_answer_now(messages=messages, client=client)
            tool_results = []
            image_messages: list[dict[str, Any]] = []
            for call_index, (tool_name, _), tool_result in zip(
                prepared_indexes,
                prepared_calls,
                executed_results,
            ):
                if tool_name == "image_read":
                    try:
                        img_data = json.loads(tool_result)
                        image_items = []
                        if img_data.get("__images__") and isinstance(img_data.get("images"), list):
                            image_items = [
                                item for item in img_data["images"]
                                if isinstance(item, dict) and item.get("__image__")
                            ]
                        elif img_data.get("__image__"):
                            image_items = [img_data]
                        if image_items:
                            tool_results.append(
                                {
                                    "index": call_index,
                                    "name": tool_name,
                                    "result": "已读取图片: " + ", ".join(
                                        str(item.get("path", "")) for item in image_items
                                    ),
                                }
                            )
                            multimodal_content: list[dict[str, Any]] = []
                            for index, item in enumerate(image_items, start=1):
                                image_path = str(item.get("path", ""))
                                image_label = f"图片 {index}: {Path(image_path).name or image_path}"
                                image_question = item.get("question") or "请描述图片内容。"
                                multimodal_content.append({
                                    "type": "text",
                                    "text": (
                                        f"{image_label}\n"
                                        f"{image_question}\n"
                                        "回答时保持这张图片与上述文件名的对应关系；不要再次读取同一批图片。"
                                    ),
                                })
                                multimodal_content.append({
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:{item['mime_type']};base64,{item['base64']}"
                                    },
                                })
                            image_messages.append({"role": "user", "content": multimodal_content})
                            continue
                    except (json.JSONDecodeError, KeyError):
                        pass
                tool_results.append(
                    {
                        "index": call_index,
                        "name": tool_name,
                        "result": tool_result,
                    }
                )

            messages.append({"role": "assistant", "content": content})
            messages.append(
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "tool_results": tool_results,
                            "instruction": "根据工具结果继续。还需要工具则输出 tool_calls JSON；完成则直接输出最终答案文本。",
                        },
                        ensure_ascii=False,
                        indent=2,
                    )[:tool_output_max_chars()],
                }
            )
            messages.extend(image_messages)

        messages.append({"role": "user", "content": "请停止请求工具，直接输出最终答案文本。"})
        completion = await client.create(messages=messages, tools=[], tool_choice="none")
        candidate = self._clean_final_answer(str(first_message(completion).get("content") or ""))
        return await self._verify_and_fix(
            candidate=candidate,
            messages=messages,
            client=client,
            tools=tools,
            context=context,
        )

    async def _execute_tool_batch(
        self,
        context: AgentContext,
        calls: list[tuple[str, dict[str, Any]]],
    ) -> list[str]:
        if len(calls) > 1 and all(
            tool_name in PARALLEL_SAFE_TOOLS
            for tool_name, _ in calls
        ):
            return list(
                await asyncio.gather(
                    *(
                        self._call_tool_as_text(context, tool_name, tool_args)
                        for tool_name, tool_args in calls
                    )
                )
            )

        results = []
        for tool_name, tool_args in calls:
            results.append(
                await self._call_tool_as_text(context, tool_name, tool_args)
            )
        return results

    async def _create_before_soft_deadline(
        self,
        client: ChatCompletionClient,
        context: AgentContext,
        **kwargs: Any,
    ) -> dict[str, Any]:
        remaining = self._soft_deadline_remaining(context)
        if remaining is None:
            return await client.create(**kwargs)
        if remaining <= 0:
            raise SoftDeadlineExceeded
        try:
            return await asyncio.wait_for(client.create(**kwargs), timeout=remaining)
        except asyncio.TimeoutError as exc:
            if (self._soft_deadline_remaining(context) or 0) <= 0:
                raise SoftDeadlineExceeded from exc
            raise

    async def _execute_before_soft_deadline(
        self,
        context: AgentContext,
        calls: list[tuple[str, dict[str, Any]]],
    ) -> list[str]:
        remaining = self._soft_deadline_remaining(context)
        if remaining is None:
            return await self._execute_tool_batch(context, calls)
        if remaining <= 0:
            raise SoftDeadlineExceeded
        try:
            return await asyncio.wait_for(
                self._execute_tool_batch(context, calls),
                timeout=remaining,
            )
        except asyncio.TimeoutError as exc:
            if (self._soft_deadline_remaining(context) or 0) <= 0:
                raise SoftDeadlineExceeded from exc
            raise

    def _soft_deadline_remaining(self, context: AgentContext) -> float | None:
        deadline = getattr(context, "soft_deadline_monotonic", None)
        if deadline is None:
            return None
        return float(deadline) - time.monotonic()

    async def _final_answer_now(
        self,
        *,
        messages: list[dict[str, Any]],
        client: ChatCompletionClient,
    ) -> str:
        final_messages = [
            *messages,
            {
                "role": "user",
                "content": (
                    "时间即将耗尽。停止调用工具和继续复查，立即根据现有信息输出最可能的最终答案。"
                    "只输出题目要求的答案，不解释，不留空。"
                ),
            },
        ]
        completion = await client.create(
            messages=final_messages,
            tools=[],
            tool_choice="none",
        )
        candidate = self._clean_final_answer(
            str(first_message(completion).get("content") or "")
        )
        return self._apply_output_format_hints(candidate, final_messages)

    async def _call_tool_as_text(self, context: AgentContext, tool_name: str, tool_args: dict[str, Any]) -> str:
        trace = get_active_trace()
        start = time.monotonic()
        error_text: str | None = None
        try:
            tool_result = await context.call_tool(tool_name, tool_args)
        except Exception as exc:
            tool_result = f"工具调用失败：{exc}"
            error_text = str(exc)
        result_text = tool_result if isinstance(tool_result, str) else json.dumps(tool_result, ensure_ascii=False)

        if trace is not None:
            try:
                trace.record_tool_call(
                    duration_ms=int((time.monotonic() - start) * 1000),
                    tool_name=tool_name,
                    arguments=tool_args,
                    result=result_text[:3000],
                    error=error_text,
                )
            except Exception:
                pass  # tracing must never break the main flow

        return result_text

    def _assistant_message_for_history(self, message: dict[str, Any]) -> dict[str, Any]:
        history_message: dict[str, Any] = {
            "role": "assistant",
            "content": message.get("content") or "",
        }
        tool_calls = self._tool_calls_from_message(message)
        if tool_calls:
            history_message["tool_calls"] = tool_calls
        return history_message

    def _tool_calls_from_message(self, message: dict[str, Any]) -> list[dict[str, Any]]:
        tool_calls = message.get("tool_calls") or []
        if tool_calls:
            normalized = []
            for tool_call in tool_calls:
                if isinstance(tool_call.get("function"), dict):
                    normalized.append(tool_call)
                else:
                    normalized.append(
                        {
                            "id": tool_call.get("id", ""),
                            "type": tool_call.get("type", "function"),
                            "function": {
                                "name": tool_call.get("name", ""),
                                "arguments": tool_call.get("arguments") or "{}",
                            },
                        }
                    )
            return normalized
        function_call = message.get("function_call")
        if isinstance(function_call, dict):
            return [
                {
                    "id": "legacy_function_call",
                    "type": "function",
                    "function": {
                        "name": function_call.get("name", ""),
                        "arguments": function_call.get("arguments") or "{}",
                    },
                }
            ]
        return []

    def _tool_call_name(self, tool_call: dict[str, Any]) -> str:
        if isinstance(tool_call.get("function"), dict):
            return str(tool_call["function"].get("name") or "")
        return str(tool_call.get("name") or "")

    def _tool_call_arguments(self, tool_call: dict[str, Any]) -> str:
        if isinstance(tool_call.get("function"), dict):
            return str(tool_call["function"].get("arguments") or "{}")
        return str(tool_call.get("arguments") or "{}")

    def _parse_json_object(self, content: str) -> dict[str, Any] | None:
        text = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
        candidates = [text]
        candidates.extend(match.group(1).strip() for match in re.finditer(r"```(?:json|tool_calls)?\s*(.*?)```", text, flags=re.DOTALL))
        object_match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if object_match:
            candidates.append(object_match.group(0))
        array_match = re.search(r"\[.*\]", text, flags=re.DOTALL)
        if array_match:
            candidates.append(array_match.group(0))

        for candidate in candidates:
            try:
                data = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                return data
            if isinstance(data, list):
                return {"tool_calls": data}
        return None

    def _clean_final_answer(self, content: str) -> str:
        # 去掉 <think> 标签及其内容
        cleaned = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
        cleaned = re.sub(r'</?think>', '', cleaned).strip()
        if not cleaned:
            return content.strip()
        return cleaned

    async def _verify_and_fix(
        self,
        *,
        candidate: str,
        messages: list[dict[str, Any]],
        client: "ChatCompletionClient",
        tools: list,
        context: "AgentContext",
    ) -> str:
        """Run one format-only check and otherwise preserve the main answer."""
        original_answer = self._clean_final_answer(candidate)
        try:
            checker_result = await self._call_tool_as_text(
                context, "agent_delegate",
                {
                    "agent_name": "answer_checker",
                    "task": original_answer,
                    "context_text": "",
                },
            )
        except Exception:
            return original_answer

        try:
            checker = json.loads(checker_result)
        except (json.JSONDecodeError, TypeError):
            return original_answer
        if not isinstance(checker, dict):
            return original_answer

        overall_valid = checker.get("overall_valid")
        if not isinstance(overall_valid, bool):
            return original_answer

        cleaned = self._non_empty_checker_answer(
            checker.get("cleaned_answer"),
            fallback=original_answer,
        )
        corrected = self._non_empty_checker_answer(
            checker.get("corrected_answer"),
            fallback="",
        )
        proposed = corrected or cleaned or original_answer
        if not self._is_format_only_correction(original_answer, proposed):
            return original_answer
        return self._apply_output_format_hints(proposed, messages)

    def _non_empty_checker_answer(self, value: Any, *, fallback: str) -> str:
        if not isinstance(value, str) or not value.strip():
            return fallback
        return self._clean_final_answer(value)

    def _is_format_only_correction(self, original: str, corrected: str) -> bool:
        """Protect already-structured answers from checker semantic rewrites."""
        if original == corrected:
            return True

        try:
            original_json = json.loads(original)
        except json.JSONDecodeError:
            original_json = None
        else:
            try:
                return json.loads(corrected) == original_json
            except json.JSONDecodeError:
                return False

        comma_item = r"[\w./:@%+~-]+"
        comma_list = rf"^{comma_item}(?:\s*,\s*{comma_item})+$"
        if re.fullmatch(comma_list, original.strip()):
            original_items = [item.strip() for item in original.split(",")]
            corrected_items = [item.strip() for item in corrected.split(",")]
            return original_items == corrected_items

        return True

    def _apply_output_format_hints(self, answer: str, messages: list[dict[str, Any]]) -> str:
        """Apply deterministic formatting hints that do not change answer content."""
        question_text = self._question_text_from_messages(messages)
        if self._requires_ascii_comma(question_text) and not self._looks_like_json_answer(answer):
            answer = answer.replace("，", ",")
        return answer

    def _question_text_from_messages(self, messages: list[dict[str, Any]]) -> str:
        parts: list[str] = []
        for message in messages:
            if message.get("role") != "user":
                continue
            content = message.get("content")
            if isinstance(content, str):
                parts.append(content)
            elif isinstance(content, list):
                parts.extend(
                    str(item.get("text", ""))
                    for item in content
                    if isinstance(item, dict) and item.get("type") == "text"
                )
        return "\n".join(parts)

    def _requires_ascii_comma(self, question_text: str) -> bool:
        return bool(
            re.search(
                r"(英文|半角|ASCII)\s*(?:逗号|comma|分隔符)|(?:逗号|comma|分隔符)\s*(?:英文|半角|ASCII)",
                question_text,
                flags=re.IGNORECASE,
            )
        )

    def _looks_like_json_answer(self, answer: str) -> bool:
        stripped = answer.strip()
        if not stripped.startswith(("{", "[")):
            return False
        try:
            json.loads(stripped)
        except json.JSONDecodeError:
            return False
        return True

    def _json_prompt_tool_calls(self, parsed: dict[str, Any]) -> list[dict[str, Any]] | None:
        tool_calls = parsed.get("tool_calls")
        if isinstance(tool_calls, list):
            return tool_calls
        if parsed.get("tool") or (parsed.get("name") and "arguments" in parsed):
            return [parsed]
        return None
