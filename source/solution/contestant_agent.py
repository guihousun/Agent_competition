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
        "answer_formatter",
        "csv_aggregate",
        "csv_read",
        "date_compute",
        "file_list",
        "mock_order_lookup",
        "mock_policy_check",
        "skill_load",
        "skill_read_resource",
        "sql_query",
        "text_read_file",
        "workday_calc",
    }
)


SYSTEM_PROMPT = """
你是 Agent 大赛的参赛 Agent。目标是在无人值守环境中独立、完整、准确地完成每道题。

【自治要求】
- 不存在人机交互。不得询问用户、等待确认或要求补充信息。
- 自行理解题意、规划步骤、选择工具、处理失败并完成验证；信息不完美时，基于现有题面和可用能力给出最佳答案。
- 推理和工具过程仅用于内部执行，不得出现在最终答案中。

【能力使用】
- question 中的 tools、skills、sub_agents 只是提示，不是权限限制；按实际需要使用 capabilities 中的可用能力。
- 文件内容不会自动进入上下文。需要证据时读取题目附件；若附件是目录，先用 file_list 查看文件清单，再读取具体文件。
- 事实、日期、计算、数据库、图片、接口响应等应以工具和输入资料为准，不得编造。
- 相对日期、星期、偏移、节日等调用 date_compute，并把包含时间锚点的完整原句作为 expression；工作日推算使用 workday_calc。
- 大型表格、数据库或文档优先使用适合的工具、Skill 或 data_reader，避免把无关全文塞入上下文。使用 Skill 时先 skill_load，再按说明 skill_run。
- 多源故障证据优先用 evidence_chain_analyze 批量关联；顺序接口用例先生成完整执行计划，再用 api_test_execute 一次执行和断言。
- Java 个税计算器相关题优先 skill_load java_tax_solver 获取修复清单和校验方法；主 Agent 自己读取源码、修复/运行/计算，不要让 Skill 直接代答。

【效率与顺序】
- 多个互不依赖的只读或纯计算工具，应在同一轮批量调用，减少模型往返。
- 工具之间存在依赖，或涉及网络请求、状态变更、代码执行、解压、Skill 执行、子 Agent 时，按依赖顺序串行执行。
- 不重复调用相同参数。调用失败时分析错误，修正参数或选择可验证的替代方案。

【关键示例】
题目附件含多条独立日期描述：先调用 text_read_file；拿到全文后，在同一轮提交所有互不依赖的 date_compute/workday_calc 调用，再按原始行序汇总。若任务是“获取 token → 写接口 → 查询结果”，每一步依赖上一步，必须串行，不能并发。

【答案责任】
- 主 Agent 独立负责答案正确性和完整性。提交前核对题目约束、证据、顺序、数量、精度和格式。
- 严格遵循本题要求的原始顺序、排序、去重、字段、分隔符和精度；不要自行套用其他题目的格式规则。
- 最终只输出答案正文。除非题目明确要求，否则不要输出解释、Markdown 代码块、<think>、过程标签或 {"answer": ...} 包装。
- JSON 必须合法；精确匹配、列表、数字或分隔符格式以题面要求为唯一准则。
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
        has_java_source = any(
            Path(file_name).name.lower().startswith("javasource_")
            and Path(file_name).suffix.lower() == ".java"
            for file_name in files
        )
        if not has_java_source or "所得税" not in question_text:
            return {}

        skill_path = Path(__file__).resolve().parent / "skills" / "java_tax_solver" / "SKILL.md"
        try:
            guidance = skill_path.read_text(encoding="utf-8")
        except OSError:
            guidance = (
                "java_tax_solver: 修复 Java 源码，动态读取源码中的税率表、起征点和题面工资用例；"
                "不要硬编码官方样例答案；参考 scripts/tax_repair_example.py 的模式，用 code_execute 的 python 模式验证。"
            )
        return {
            "task_guidance": guidance[:8000],
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

            completion = await client.create(messages=messages, tools=tools, tool_choice="auto")
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

            tool_results = await self._execute_tool_batch(context, prepared_calls)
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
                        if img_data.get("__image__"):
                            # Add tool result with summary
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.get("id", ""),
                                "name": tool_name,
                                "content": f"已读取图片: {img_data['path']}",
                            })
                            # Inject image as multimodal user message
                            messages.append({
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": img_data.get("question", "请描述这张图片")},
                                    {
                                        "type": "image_url",
                                        "image_url": {
                                            "url": f"data:{img_data['mime_type']};base64,{img_data['base64']}"
                                        },
                                    },
                                ],
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
            completion = await client.create(messages=messages, tools=[], tool_choice="none")
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

            executed_results = await self._execute_tool_batch(context, prepared_calls)
            tool_results = []
            for call_index, (tool_name, _), tool_result in zip(
                prepared_indexes,
                prepared_calls,
                executed_results,
            ):
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
        """Run two format checks, then one tool-less main-model format repair."""
        original_answer = self._clean_final_answer(candidate)
        working_answer = original_answer
        format_issues: list[str] = []
        check_rounds = min(max(env_int("AGENT_DEMO_MAX_FIX_ROUNDS", 2), 1), 2)

        for check_round in range(check_rounds):
            checker_result = await self._call_tool_as_text(
                context, "agent_delegate",
                {
                    "agent_name": "answer_checker",
                    "task": working_answer,
                    "context_text": "",
                },
            )

            try:
                checker = json.loads(checker_result)
            except (json.JSONDecodeError, TypeError):
                if check_round + 1 < check_rounds:
                    continue
                return original_answer
            if not isinstance(checker, dict):
                if check_round + 1 < check_rounds:
                    continue
                return original_answer

            overall_valid = checker.get("overall_valid")
            if not isinstance(overall_valid, bool):
                if check_round + 1 < check_rounds:
                    continue
                return original_answer

            cleaned = self._non_empty_checker_answer(
                checker.get("cleaned_answer"),
                fallback=working_answer,
            )
            corrected = self._non_empty_checker_answer(
                checker.get("corrected_answer"),
                fallback="",
            )
            if overall_valid:
                final_answer = corrected or cleaned or working_answer
                if self._is_format_only_correction(working_answer, final_answer):
                    return final_answer
                format_issues = ["checker 尝试改变结构化答案内容，已拒绝该修改"]
                continue

            issues = checker.get("format_issues", checker.get("fix_suggestions", []))
            if isinstance(issues, list):
                format_issues = [str(item) for item in issues if str(item).strip()]

            proposed = corrected or cleaned
            if (
                proposed
                and proposed != working_answer
                and self._is_format_only_correction(working_answer, proposed)
            ):
                working_answer = proposed

        issue_text = "\n".join(f"- {item}" for item in format_issues) or "- 格式检查未通过"
        fix_prompt = (
            "只修复格式：修复下面候选答案的最终输出格式，不得重新解题，不得重新计算，"
            "不得调用工具，不得增加、删除或替换事实值、数字、日期、ID 或列表成员。\n"
            "可修复 Markdown 代码块、<think>、JSON 语法、引号、括号、转义、"
            "题目明确要求的分隔符和输出结构。\n\n"
            f"格式问题：\n{issue_text}\n\n"
            f"候选答案：\n{working_answer}\n\n"
            "只输出修复后的完整答案正文；无法仅靠格式修复时原样输出候选答案。"
        )
        format_messages = [
            *messages,
            {"role": "user", "content": fix_prompt},
        ]
        try:
            completion = await client.create(
                messages=format_messages,
                tools=[],
                tool_choice="none",
            )
            repaired = self._clean_final_answer(
                str(first_message(completion).get("content") or "")
            )
        except Exception:
            return original_answer

        if not repaired:
            return original_answer
        if not self._is_format_only_correction(working_answer, repaired):
            return original_answer
        return repaired

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

    def _json_prompt_tool_calls(self, parsed: dict[str, Any]) -> list[dict[str, Any]] | None:
        tool_calls = parsed.get("tool_calls")
        if isinstance(tool_calls, list):
            return tool_calls
        if parsed.get("tool") or (parsed.get("name") and "arguments" in parsed):
            return [parsed]
        return None
