"""Non-invasive tracing for the agent contest demo.

Uses contextvars.ContextVar for async-safe propagation.
When no trace is active, all recording calls are no-ops (zero overhead).
"""

from __future__ import annotations

import json
import time
import uuid
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class SpanEvent:
    """A single observable event (LLM call or tool call)."""

    type: str  # "llm_call" | "tool_call"
    seq: int
    timestamp: str
    duration_ms: int
    data: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class QuestionTrace:
    """Trace for a single question."""

    id: str
    title: str = ""
    description: str = ""
    status: str = "running"  # "running" | "success" | "error"
    answer: str = ""
    error: str | None = None
    duration_ms: int = 0
    spans: list[SpanEvent] = field(default_factory=list)
    tokens: dict[str, int] = field(default_factory=lambda: {"prompt": 0, "completion": 0})
    _seq_counter: int = field(default=0, repr=False)
    _start_time: float = field(default=0.0, repr=False)

    def _next_seq(self) -> int:
        self._seq_counter += 1
        return self._seq_counter - 1

    def record_llm_call(
        self,
        *,
        duration_ms: int,
        model: str,
        messages_count: int,
        tools_count: int,
        output_preview: str,
        tool_calls: list[dict[str, Any]],
        usage: dict[str, Any] | None,
        finish_reason: str | None,
    ) -> None:
        """Record an LLM call span."""
        # Extract simplified tool call info
        simplified_calls = []
        for tc in tool_calls:
            func = tc.get("function", tc)
            simplified_calls.append({
                "name": str(func.get("name", "")),
                "arguments": str(func.get("arguments", ""))[:500],
            })

        span = SpanEvent(
            type="llm_call",
            seq=self._next_seq(),
            timestamp=_now_iso(),
            duration_ms=duration_ms,
            data={
                "model": model,
                "messages_count": messages_count,
                "tools_count": tools_count,
                "output_preview": output_preview[:1000],
                "tool_calls": simplified_calls,
                "usage": usage or {},
                "finish_reason": finish_reason,
            },
        )
        self.spans.append(span)

        # Accumulate tokens
        if usage:
            self.tokens["prompt"] = self.tokens.get("prompt", 0) + int(usage.get("prompt_tokens", 0) or 0)
            self.tokens["completion"] = self.tokens.get("completion", 0) + int(usage.get("completion_tokens", 0) or 0)

    def record_tool_call(
        self,
        *,
        duration_ms: int,
        tool_name: str,
        arguments: dict[str, Any],
        result: str,
        error: str | None,
    ) -> None:
        """Record a tool call span."""
        # Classify tool type for dashboard coloring
        tool_type = _classify_tool(tool_name)

        span = SpanEvent(
            type="tool_call",
            seq=self._next_seq(),
            timestamp=_now_iso(),
            duration_ms=duration_ms,
            data={
                "tool_name": tool_name,
                "tool_type": tool_type,
                "arguments": _truncate_dict(arguments, 2000),
                "result": result[:3000],
                "error": error,
            },
        )
        self.spans.append(span)

    def finish(self, status: str, answer: str, duration_ms: int, *, error: str | None = None) -> None:
        self.status = status
        self.answer = answer
        self.duration_ms = duration_ms
        self.error = error

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "answer": self.answer,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "tokens": self.tokens,
            "spans": [s.to_dict() for s in self.spans],
        }


# ---------------------------------------------------------------------------
# ContextVar-based propagation
# ---------------------------------------------------------------------------

_active_trace: ContextVar[QuestionTrace | None] = ContextVar("_active_trace", default=None)


def get_active_trace() -> QuestionTrace | None:
    """Return the currently active question trace, or None."""
    return _active_trace.get()


def begin_question_trace(question_id: str, title: str = "", description: str = "") -> QuestionTrace:
    """Start a new question trace and set it as the active context."""
    trace = QuestionTrace(id=question_id, title=title, description=description[:500], _start_time=time.monotonic())
    _active_trace.set(trace)
    return trace


def end_question_trace(
    status: str,
    answer: str,
    *,
    error: str | None = None,
) -> None:
    """Finish the active question trace."""
    trace = _active_trace.get()
    if trace is None:
        return
    elapsed = int((time.monotonic() - trace._start_time) * 1000)
    trace.finish(status, answer, elapsed, error=error)
    _active_trace.set(None)


# ---------------------------------------------------------------------------
# Run-level aggregation and persistence
# ---------------------------------------------------------------------------

@dataclass
class RunTrace:
    """Aggregate trace for an entire run."""

    run_id: str
    model: str
    start_time: str
    questions: list[QuestionTrace] = field(default_factory=list)
    total_duration_ms: int = 0

    def add_question(self, trace: QuestionTrace) -> None:
        self.questions.append(trace)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "model": self.model,
            "start_time": self.start_time,
            "total_duration_ms": self.total_duration_ms,
            "questions": [q.to_dict() for q in self.questions],
        }

    def flush_to_file(self, path: str | Path) -> None:
        """Write trace data to a JSON file atomically."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
            f.write("\n")
        tmp.replace(path)


def create_run_trace(model: str) -> RunTrace:
    """Create a new run-level trace."""
    now = datetime.now(timezone.utc)
    return RunTrace(
        run_id=f"run_{now.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}",
        model=model,
        start_time=now.isoformat(),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _classify_tool(tool_name: str) -> str:
    """Classify a tool name for dashboard coloring."""
    if tool_name in ("skill_load", "skill_read_resource", "skill_run"):
        return "skill"
    if tool_name == "agent_delegate":
        return "agent"
    if tool_name == "text_read_file":
        return "file"
    return "tool"


def _truncate_dict(data: Any, max_chars: int) -> Any:
    """Truncate string values in a dict for display."""
    if isinstance(data, str):
        return data[:max_chars] if len(data) > max_chars else data
    if isinstance(data, dict):
        return {k: _truncate_dict(v, max_chars) for k, v in data.items()}
    if isinstance(data, list):
        return [_truncate_dict(v, max_chars) for v in data]
    return data
