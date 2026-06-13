from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

from source.runtime.env_config import ModelConfig, env_int
from source.runtime.openai_chat_client import ChatCompletionClient, first_message


AGENTS_DIR = Path(__file__).resolve().parent / "agents"
ToolRunner = Callable[[str, dict[str, Any]], Awaitable[Any]]


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


@dataclass
class BaseSubAgent:
    name: str
    role: str

    async def run(
        self,
        *,
        task: str,
        context_text: str = "",
        runtime_context: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_runner: ToolRunner | None = None,
    ) -> str:
        raise NotImplementedError


@dataclass
class ScriptSubAgent(BaseSubAgent):
    agent_dir: Path
    entrypoint: str
    timeout_seconds: int
    allowed_tools: tuple[str, ...] = ()
    tools_enabled: bool = True

    async def run(
        self,
        *,
        task: str,
        context_text: str = "",
        runtime_context: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_runner: ToolRunner | None = None,
    ) -> str:
        runtime_context = runtime_context or {}
        prompt_package = await asyncio.to_thread(
            self._build_prompt_package,
            task,
            context_text,
            runtime_context,
        )
        instruction = str(prompt_package.pop("instruction", "")).strip()
        if not instruction:
            raise RuntimeError(f"Sub-agent did not provide an instruction: {self.name}")

        client = ChatCompletionClient(ModelConfig.from_env())
        available_tools = []
        if self.tools_enabled:
            available_tools = [
                tool
                for tool in (tools or [])
                if not self.allowed_tools
                or str(tool.get("function", {}).get("name") or "") in self.allowed_tools
            ]
        operating_rule = (
            "不得调用工具、读取文件或重新解题，只能检查并修复答案格式。"
            if not self.tools_enabled
            else "必须基于给定题目、上下文和工具结果工作。"
        )
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    f"你是 {self.role}。\n\n{instruction}\n\n"
                    f"{operating_rule}"
                    "最终只输出要求的 JSON，不要输出 markdown 代码块或思考过程。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(prompt_package, ensure_ascii=False, indent=2),
            },
        ]

        max_iterations = 12
        for _ in range(max_iterations):
            tool_choice = "auto" if available_tools else "none"
            completion = await client.create(
                messages=messages,
                tools=available_tools,
                tool_choice=tool_choice,
            )
            message = first_message(completion)
            tool_calls = _tool_calls_from_message(message)
            content = str(message.get("content") or "").strip()
            messages.append(_assistant_message_for_history(message, tool_calls))

            if not tool_calls:
                return _extract_json_text(content)
            if tool_runner is None:
                raise RuntimeError(f"Sub-agent requested tools without a tool runner: {self.name}")

            for tool_call in tool_calls:
                tool_name = str(tool_call["function"].get("name") or "")
                try:
                    tool_args = json.loads(tool_call["function"].get("arguments") or "{}")
                except json.JSONDecodeError:
                    tool_args = {}
                if not isinstance(tool_args, dict):
                    tool_args = {}
                result = await tool_runner(tool_name, tool_args)
                result_text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.get("id", ""),
                        "name": tool_name,
                        "content": result_text[: env_int("AGENT_DEMO_TOOL_OUTPUT_MAX_CHARS", 65_536)],
                    }
                )

        raise RuntimeError(f"Sub-agent exceeded tool iteration limit: {self.name}")

    def _build_prompt_package(
        self,
        task: str,
        context_text: str,
        runtime_context: dict[str, Any],
    ) -> dict[str, Any]:
        script_path = (self.agent_dir / self.entrypoint).resolve()
        if not script_path.exists():
            raise FileNotFoundError(f"Sub-agent entrypoint not found: {script_path}")

        question = runtime_context.get("question")
        if not isinstance(question, dict):
            question = {}
        files = question.get("files") or []
        payload = {
            "agent_name": self.name,
            "role": self.role,
            "task": task,
            "context_text": context_text,
        }
        if self.name == "answer_checker":
            payload["question"] = question
            payload["answer"] = task
        elif self.name == "data_reader":
            payload["question"] = task
            payload["files"] = files
            payload["mode"] = _infer_data_reader_mode(task)

        completed = subprocess.run(
            [sys.executable, str(script_path)],
            input=json.dumps(payload, ensure_ascii=False),
            text=True,
            encoding="utf-8",
            errors="strict",
            capture_output=True,
            cwd=str(self.agent_dir),
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            timeout=self.timeout_seconds,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"Sub-agent script failed: {script_path}\n"
                f"exit_code={completed.returncode}\n"
                f"stderr={completed.stderr.strip()}"
            )
        try:
            result = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Sub-agent prompt builder returned invalid JSON: {script_path}"
            ) from exc
        if not isinstance(result, dict):
            raise RuntimeError(f"Sub-agent prompt builder returned non-object JSON: {script_path}")
        return result


def _infer_data_reader_mode(task: str) -> str:
    normalized = task.lower()
    overview_markers = ("overview", "探查", "概览", "结构", "schema", "全貌")
    return "overview" if any(marker in normalized for marker in overview_markers) else "query"


def _tool_calls_from_message(message: dict[str, Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, tool_call in enumerate(message.get("tool_calls") or []):
        if not isinstance(tool_call, dict):
            continue
        function = tool_call.get("function")
        if not isinstance(function, dict):
            function = {
                "name": tool_call.get("name", ""),
                "arguments": tool_call.get("arguments") or "{}",
            }
        normalized.append(
            {
                "id": tool_call.get("id") or f"sub_agent_tool_{index}",
                "type": "function",
                "function": {
                    "name": str(function.get("name") or ""),
                    "arguments": str(function.get("arguments") or "{}"),
                },
            }
        )
    return normalized


def _assistant_message_for_history(
    message: dict[str, Any],
    tool_calls: list[dict[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "role": "assistant",
        "content": message.get("content") or "",
    }
    if tool_calls:
        result["tool_calls"] = tool_calls
    return result


def _extract_json_text(content: str) -> str:
    stripped = content.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        stripped = stripped[3:-3].strip()
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Sub-agent returned invalid JSON: {content[:500]}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("Sub-agent must return a JSON object.")
    return json.dumps(parsed, ensure_ascii=False)


def _load_agent_package(agent_dir: Path) -> ScriptSubAgent | None:
    metadata_path = agent_dir / "agent.json"
    if not metadata_path.exists():
        return None
    metadata = _load_json(metadata_path)
    return ScriptSubAgent(
        name=metadata["name"],
        role=metadata.get("role", metadata.get("description", "")),
        agent_dir=agent_dir,
        entrypoint=metadata.get("entrypoint", "scripts/run.py"),
        timeout_seconds=int(metadata.get("timeout_seconds", 30)),
        allowed_tools=tuple(str(name) for name in metadata.get("allowed_tools", [])),
        tools_enabled=bool(metadata.get("tools_enabled", True)),
    )


def build_sub_agents() -> dict[str, BaseSubAgent]:
    agents: dict[str, BaseSubAgent] = {}
    if not AGENTS_DIR.exists():
        return agents
    for agent_dir in sorted(path for path in AGENTS_DIR.iterdir() if path.is_dir()):
        agent = _load_agent_package(agent_dir)
        if agent is not None:
            agents[agent.name] = agent
    return agents
