from __future__ import annotations

from typing import Any, Awaitable, Callable


class AgentRegistry:
    def __init__(self) -> None:
        from source.solution.sub_agents import build_sub_agents

        self._agents = build_sub_agents()

    def names(self) -> list[str]:
        return sorted(self._agents)

    async def run(
        self,
        *,
        agent_name: str,
        task: str,
        context_text: str = "",
        runtime_context: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_runner: Callable[[str, dict[str, Any]], Awaitable[Any]] | None = None,
    ) -> str:
        if agent_name not in self._agents:
            raise KeyError(f"Unknown agent: {agent_name}")
        return await self._agents[agent_name].run(
            task=task,
            context_text=context_text,
            runtime_context=runtime_context,
            tools=tools,
            tool_runner=tool_runner,
        )
