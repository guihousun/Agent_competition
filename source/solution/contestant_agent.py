from __future__ import annotations

import json
import re
import time
from typing import Any

from source.runtime.env_config import ModelConfig, env_bool, env_int, load_dotenv
from source.runtime.agent_context import AgentContext
from source.runtime.openai_chat_client import ChatCompletionClient, first_message
from source.runtime.tracing import get_active_trace


SYSTEM_PROMPT = """
你是 skill 蒸馏攻防 Agent 大赛的参赛 Agent。

使用 ReAct（Reasoning + Acting）框架解题：

【ReAct 流程】
1. Thought: 分析题目，确定解题策略和需要的工具
2. Action: 调用工具执行
3. Observation: 分析工具返回结果
4. 重复 1-3 直到获得足够信息
5. Answer: 输出最终答案（严格遵守格式规则）

【工具选择策略】
- 读取文件 → text_read_file
- 数据分析/聚合 → data_analyzer skill（先 skill_load）
- 文档搜索 → document_searcher skill（先 skill_load）
- HTTP 请求 → http_request
- 代码执行 → code_execute
- 压缩包解压 → zip_extract / tar_extract
- 答案格式化 → answer_formatter


【路径管理规范】（必须严格遵守）

1. 工作目录：当前工作目录是项目根目录
2. 题目文件路径：使用题目 files 字段中声明的路径（相对路径）
   - ✓ files/nested_archive.zip
   - ✗ ./source/examples/files/nested_archive.zip
   - ✗ D:\Research_vault\...
ested_archive.zip
3. 工具返回的路径：直接使用，不要修改
   - zip_extract 返回 output_dir，直接用这个路径读取文件
   - 不要自己猜测或拼接路径
4. 解压文件：在 zip_extract 返回的 output_dir 中查找
   - 不要假设解压到当前目录
   - 不要尝试其他路径
5. 路径拼接：使用正斜杠 / 或双反斜杠 \
   - ✓ output_dir/config.json
   - ✓ output_dir\config.json
   - ✗ output_dir\config.json（单反斜杠可能转义）

【Skill 使用流程】
1. skill_load 加载 skill（获取完整说明）
2. 按 SKILL.md 指示调用 skill_run
3. 分析结果

【关键原则】
- 每次只调用一个工具，等待结果后再决定下一步
- 如果工具调用失败，分析错误原因并尝试替代方案
- 不要重复调用相同参数的工具
- 文件路径使用题目中声明的路径，不要尝试其他路径

【答案格式规则】（必须严格遵守，违反则不得分）

1. 只输出答案正文，不要：
   - 解释说明（"答案是..."、"根据分析..."）
   - Markdown 代码块（```json ... ```）
   - <think> 标签
   - 结果对象包装（{"answer": "..."}）

2. 根据题目类型选择格式：

   a) 精确匹配题：
      - 直接输出文本本身，去除首尾空白
      - ✓ mock-file-read-ok
      -  "mock-file-read-ok"
      - ✗ 答案是：mock-file-read-ok

   b) JSON 字段匹配题：
      - 输出严格 JSON，字段按字母顺序排列
      - ✓ {"amount": 100, "supplier": "A"}
      - ✗ {"supplier": "A", "amount": 100}

   c) 列表匹配题：
      - 输出 JSON 数组，元素排序去重
      - ✓ ["A", "B", "C"]
      - ✗ ["C", "A", "B"]
      -  ["A", "B", "B", "C"]

   d) 数字答案：
      - 不要单位，不要千分位
      - 保留题目要求的精度
      - ✓ 1234.56
      - ✗ 1,234.56
      - ✗ 1234.56 元

3. 如果不确定格式，调用 answer_formatter 工具格式化

4. 最终输出前自检：
   - 是否有遗漏的字段？
   - 列表是否完整？
   - 数字精度是否正确？

最终只输出题目要求的答案正文。不要输出思考过程、markdown、代码块、<think> 标签、结果对象或额外元数据字段。
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
        # - context 提供当前 solution 自动发现到的 MCP tools、skills、sub-agents 以及 call_tool(...) 调用入口。
        # - available_tools / available_skills / available_sub_agents 会一起传给模型，供主 Agent 自己决定是否调用。
        user_prompt = json.dumps(
            {
                "question": question,
                "files": question.get("files") or [],
                "available_tools": context.available_tools,
                "available_skills": context.available_skills,
                "available_sub_agents": context.available_agents,
                "tool_usage": "Call tools only when useful. Use text_read_file to read declared files; use skill_load before skill_run; use agent_delegate for sub-agents.",
                "final_output": "Return only the final answer text.",
            },
            ensure_ascii=False,
            indent=2,
        )

        return await self._run_model_loop(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            context=context,
        )

    async def _run_model_loop(self, *, system_prompt: str, user_prompt: str, context: AgentContext) -> str:
        if not env_bool("AGENT_DEMO_NATIVE_TOOLS", True):
            return await self._run_json_tool_loop(system_prompt=system_prompt, user_prompt=user_prompt, context=context)

        try:
            return await self._run_native_tool_loop(system_prompt=system_prompt, user_prompt=user_prompt, context=context)
        except Exception:
            if env_bool("AGENT_DEMO_JSON_TOOL_FALLBACK", True):
                try:
                    return await self._run_json_tool_loop(system_prompt=system_prompt, user_prompt=user_prompt, context=context)
                except Exception:
                    pass
            raise

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

        max_iter = env_int("AGENT_DEMO_MAX_ITER", 100)
        final_answer: str | None = None
        for step in range(1, max_iter + 1):
            completion = await client.create(messages=messages, tools=tools, tool_choice="auto")
            message = first_message(completion)
            tool_calls = self._tool_calls_from_message(message)
            content = str(message.get("content") or "")

            messages.append(self._assistant_message_for_history(message))
            if not tool_calls:
                if content.strip():
                    # 自检：保存候选答案，多一轮验证
                    if final_answer is None and step < max_iter - 1:
                        final_answer = self._clean_final_answer(content)
                        messages.append({
                            "role": "user",
                            "content": (
                                "自检：请验证上述答案是否满足题目要求。\n"
                                "检查点：\n"
                                "1. 是否直接回答了问题？\n"
                                "2. 是否满足格式要求？\n"
                                "3. 是否遗漏关键信息？\n"
                                "如果发现问题，调用工具修正后输出新答案；"
                                "如果确认无误，回复 VERIFIED。"
                            ),
                        })
                        continue
                    # 第二轮：LLM 回复 VERIFIED 或新答案
                    if final_answer is not None:
                        if content.strip().upper() == "VERIFIED":
                            return final_answer
                        # LLM 给出了修正后的答案
                        return self._clean_final_answer(content)
                    return self._clean_final_answer(content)
                messages.append({"role": "user", "content": "请输出最终答案文本。"})
                continue

            for tool_call in tool_calls:
                tool_name = self._tool_call_name(tool_call)
                args_text = self._tool_call_arguments(tool_call)
                try:
                    tool_args = json.loads(args_text)
                except json.JSONDecodeError:
                    tool_args = {}
                tool_result = await self._call_tool_as_text(context, tool_name, tool_args)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.get("id", ""),
                        "name": tool_name,
                        "content": tool_result[:12000],
                    }
                )

        messages.append({"role": "user", "content": "请停止调用工具，直接输出最终答案文本。"})
        completion = await client.create(messages=messages, tools=[], tool_choice="none")
        return self._clean_final_answer(str(first_message(completion).get("content") or ""))

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

        max_iter = env_int("AGENT_DEMO_MAX_ITER", 6)
        for step in range(1, max_iter + 1):
            completion = await client.create(messages=messages, tools=[], tool_choice="none")
            content = str(first_message(completion).get("content") or "").strip()

            parsed = self._parse_json_object(content)
            tool_calls = self._json_prompt_tool_calls(parsed) if parsed else None
            if not tool_calls:
                if content:
                    return self._clean_final_answer(content)
                messages.append({"role": "user", "content": "请输出最终答案文本，或输出 tool_calls JSON。"})
                continue

            tool_results = []
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
                tool_results.append(
                    {
                        "index": call_index,
                        "name": tool_name,
                        "result": await self._call_tool_as_text(context, tool_name, tool_args),
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
                    )[:16000],
                }
            )

        messages.append({"role": "user", "content": "请停止请求工具，直接输出最终答案文本。"})
        completion = await client.create(messages=messages, tools=[], tool_choice="none")
        return self._clean_final_answer(str(first_message(completion).get("content") or ""))

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
        cleaned = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
        return cleaned or content.strip()

    def _json_prompt_tool_calls(self, parsed: dict[str, Any]) -> list[dict[str, Any]] | None:
        tool_calls = parsed.get("tool_calls")
        if isinstance(tool_calls, list):
            return tool_calls
        if parsed.get("tool") or (parsed.get("name") and "arguments" in parsed):
            return [parsed]
        return None
