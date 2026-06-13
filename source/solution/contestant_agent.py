from __future__ import annotations

import json
import re
import time
from typing import Any

from source.runtime.env_config import ModelConfig, env_bool, env_int, load_dotenv
from source.runtime.agent_context import AgentContext
from source.runtime.openai_chat_client import ChatCompletionClient, first_message
from source.runtime.tracing import get_active_trace
from source.runtime.context_compressor import should_compress, compress_messages, estimate_messages_tokens


def tool_output_max_chars() -> int:
    return env_int("AGENT_DEMO_TOOL_OUTPUT_MAX_CHARS", 65_536)


def _tool_output_for_history(content: str) -> str:
    return content[:tool_output_max_chars()]


SYSTEM_PROMPT = """
你是 skill 蒸馏攻防 Agent 大赛的参赛 Agent。

【核心规则】
- 工具调用和推理过程不要输出到最终答案中
- 最终答案只包含题目要求的内容，不要有 Thought/Action/Observation/Final Answer 等标签
- 内部推理过程对用户不可见

使用 Plan → Execute 框架解题：

【Phase 1：规划】
收到题目后，在内部完成规划（不要输出）：
1. 题目类型判断
2. 需要读取哪些文件
3. 是否有大量数据需要 data_reader 预读
4. 执行步骤拆解
5. 预期答案格式

【Phase 2：执行】
按规划逐步调用工具，每步在内部思考（不要输出 Thought/Action/Observation）

【Phase 3：验证】
主 Agent 自己负责答案正确性；输出前通过 answer_checker 只检查最终格式

【数据处理策略】（关键，减少上下文膨胀）

遇到 CSV/DB/日志等大文件时，使用 data_reader 子代理分两阶段处理：

阶段 1：数据探查（mode="overview"）
  agent_delegate(agent_name="data_reader",
                 task="探查数据结构",
                 context_text="文件路径")

  data_reader 返回数据全貌：schema、行数、字段、值域、关联关系
  → 不做任何筛选，你基于全貌决定下一步

阶段 2：精确查询（mode="query"）
  agent_delegate(agent_name="data_reader",
                 task="具体查询指令，如：找出 status=已完成 且 amount>=50000 的行",
                 context_text="文件路径")

  data_reader 执行精确查询，返回结构化结果

何时用 data_reader：
- CSV > 50 行 → 先 overview，再 query
- SQLite 数据库 → overview 返回表结构，query 执行 SQL
- 多封邮件/日志 → overview 返回结构，query 提取关键段落

何时直接读：
- 小文件（<50行）→ text_read_file 直接读
- 已知精确行范围 → csv_read 带 offset/limit

【工具选择策略】
- 读取小文件 → text_read_file
- 读取图片（PNG/JPG/BMP/GIF/WebP） → image_read（自动调用视觉模型识别内容）
- 预读大文件 → data_reader 子代理（agent_delegate）
- 日期计算（明天/下周X/去年今天/N天后） → date_compute
- 工作日计算（N 个工作日后） → workday_calc
- 数据分析/聚合 → data_analyzer skill（先 skill_load）
- 文档搜索 → document_searcher skill（先 skill_load）
- HTTP 请求 → http_request
- 代码执行 → code_execute
- 压缩包解压 → zip_extract / tar_extract
- 数据库查询 → sql_query
- 答案格式化 → answer_formatter

【Few-shot 示例】

示例 1 - 日期计算（必须用工具）：
题目："今天是 2026-05-06，帮我算下周二是几号"
❌ 错误：直接心算回答 2026-05-13
✓ 正确：
  1. 调用 date_compute(expression="下周二是几号", base_date="2026-05-06")
  2. 工具返回 {"result": "2026-05-12"}
  3. 输出 2026-05-12

示例 2 - 工作日计算（必须用工具）：
题目："2026-12-21 后 5 个工作日是哪天"
❌ 错误：直接心算回答 2026-12-26（12-25 是圣诞节，算法未知）
✓ 正确：
  1. 调用 workday_calc(start_date="2026-12-21", days=5)
  2. 工具返回 {"result": "2026-12-28"}
  3. 输出 2026-12-28

示例 3 - 数据库查询（必须用工具）：
题目："查 chat_history.db 中所有包含 'DevPilot' 的消息"
❌ 错误：编造 SQL 或跳过查询
✓ 正确：
  1. 调用 sql_query(db_path="chat_history.db",
                    query="SELECT * FROM messages WHERE content LIKE '%DevPilot%'")
  2. 工具返回结果数组
  3. 基于结果回答

示例 4 - 图片识别（必须用工具）：
题目："读取 error_screenshot.png 中的错误信息"
❌ 错误：跳过图片或编造内容
✓ 正确：
  1. 调用 image_read(path="error_screenshot.png", question="图片中显示了什么错误信息？")
  2. 工具返回 {"description": "图片显示 NullPointerException at line 42..."}
  3. 基于描述回答

【关键原则】

【Skill 使用流程】
1. skill_load 加载 skill（获取完整说明）
2. 按 SKILL.md 指示调用 skill_run
3. 分析结果

【关键原则】
- 每次只调用一个工具，等待结果后再决定下一步
- 如果工具调用失败，分析错误原因并尝试替代方案
- 不要重复调用相同参数的工具
- 文件路径使用题目中声明的路径，不要尝试其他路径

【日期计算规则】（极易出错，必须严格遵守）

所有日期相关计算必须调用工具，不得自行心算！

必须调用 date_compute 工具的场景：
- 相对日期：明天/后天/昨天/前天/大后天
- 星期计算：上周X/下周X/本周X/这周X
- 年份计算：去年今天/明年今天/N年后
- 偏移计算：N天后/N周后/N小时后
- 节日查询：儿童节/圣诞节/元旦/春节
- 周次计算：第N周/N周后是几号

调用 date_compute 时：
- expression 必须传入题目中的完整原句，不能只截取“100小时后”“上周二”“第2周的周五”等片段
- 原句包含具体小时、周次起点或相对日期锚点时，必须保留这些信息
- base_date 只用于补充明确基准，不得替代原句中的时间和语义上下文

必须调用 workday_calc 工具的场景：
- "N 个工作日后"
- "工作日推算"
- "自然日 vs 工作日"

【日期计算常见错误】
1. "下周二" 不是 "下下周二"，是本周之后的第一个周二
2. "上周四" 不是 "上上周四"，是本周之前的最后一个周四
3. 5月6日(周三) 的 "下周二" = 5月12日（5月6日+6天），不是5月13日
4. 跨年日期需要正确处理年份（如"去年今天"从12月算到1月）

【自检强化】
在自检阶段，必须逐一核对：
1. 日期题：是否所有日期计算都调用了 date_compute / workday_calc 工具？
2. 数字题：是否所有数字都精确（无千分位、无单位）？
3. 列表题：是否排序去重？
4. 字段匹配：JSON 字段是否按字母顺序？

【Answer Checker 使用流程】

主 Agent 独立负责答案正确性。完成解题后，answer_checker 只做格式后检查：

1. 调用 agent_delegate:
   - agent_name: "answer_checker"
   - task: 最终候选答案
   - context_text: ""

2. 分析 answer_checker 返回：
   - overall_valid: true → 输出 cleaned_answer
   - overall_valid: false → 使用 corrected_answer 做一次格式修复并复检

3. answer_checker 不得调用工具、读取文件、重新计算或修改事实、数字、日期、ID、列表成员
4. 如果两次格式检查仍未通过，主模型只允许无工具修复一次格式
5. checker 失败、返回非法 JSON 或空内容时，保留主 Agent 原答案

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
      - ✗ ["A", "B", "B", "C"]

   d) 逗号分隔题：
      - 只输出逗号分隔的值，不要表格、不要说明、不要"VERIFIED"
      - ✓ PO-001,PO-002,PO-003
      - ✗ | PO | 原因 |\n|---|---|\nPO-001,PO-002

   e) 数字答案：
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
        # - question 中的 tools/skills/sub_agents 是赛题提示，不会限制默认开放的能力。
        # - context 提供当前 solution 自动发现到的 MCP tools、skills、sub-agents 以及 call_tool(...) 调用入口。
        # - available_tools / available_skills / available_sub_agents 会一起传给模型，供主 Agent 自己决定是否调用。
        user_prompt = json.dumps(
            {
                "question": question,
                "files": question.get("files") or [],
                "available_tools": context.available_tools,
                "available_skills": context.available_skills,
                "available_sub_agents": context.available_agents,
                "question_field_usage": "Treat question tools, skills, and sub_agents as useful hints, not restrictions. You may use any available capability when it helps solve the task.",
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

        max_iter = env_int("AGENT_DEMO_MAX_ITER", 30)
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

            for tool_call in tool_calls:
                tool_name = self._tool_call_name(tool_call)
                args_text = self._tool_call_arguments(tool_call)
                try:
                    tool_args = json.loads(args_text)
                except json.JSONDecodeError:
                    tool_args = {}
                tool_result = await self._call_tool_as_text(context, tool_name, tool_args)

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
