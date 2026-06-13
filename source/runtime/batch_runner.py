from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys
import tempfile
import time
from typing import Any, Callable

from source.runtime.agent_context import AgentContext
from source.runtime.agent_registry import AgentRegistry
from source.runtime.mcp_client import LocalMCPClient
from source.runtime.question_loader import load_questions
from source.runtime.question_schema import public_question_fields
from source.runtime.result_writer import write_results
from source.runtime.tracing import (
    begin_question_trace,
    create_run_trace,
    end_question_trace,
)
from source.runtime.env_config import ModelConfig, env_int, load_dotenv
from source.solution.contestant_agent import ContestantAgent


QUESTION_TIMEOUT_SECONDS = 10 * 60


class BatchRunner:
    def __init__(self) -> None:
        self.mcp = LocalMCPClient(agent_registry=AgentRegistry())
        load_dotenv()
        self._config = ModelConfig.from_env()
        self._run_trace = create_run_trace(model=self._config.model)

    async def run_file(
        self,
        *,
        question_path: str | Path,
        output_path: str | Path,
        dashboard: bool = False,
    ) -> list[dict[str, Any]]:
        question_path = Path(question_path).resolve()
        output_path = Path(output_path).resolve()
        questions = load_questions(question_path)
        question_dir = question_path.parent
        results: list[dict[str, Any]] = [
            {
                "id": str(question.get("id", index)),
                "answer": "",
            }
            for index, question in enumerate(questions, start=1)
        ]
        run_start = time.monotonic()

        write_results(output_path, results)
        self._refresh_dashboard(
            enabled=dashboard,
            questions=questions,
            current_question_id=None,
            output_path=output_path,
        )
        self._print_event(
            "RUN_START",
            {
                "questions": len(questions),
                "results_written": 0,
                "result_path": str(output_path),
                "result_bytes": self._file_size(output_path),
            },
        )

        for index, question in enumerate(questions, start=1):
            qid = str(question.get("id", index))
            title = str(question.get("title", ""))
            description = str(question.get("description", ""))
            question_timeout = self._question_timeout_seconds()
            self._print_event(
                "QUESTION_START",
                {
                    "id": qid,
                    "index": index,
                    "total": len(questions),
                    "cumulative_ms": self._elapsed_ms(run_start),
                    "timeout_seconds": question_timeout,
                },
            )
            self._refresh_dashboard(
                enabled=dashboard,
                questions=questions,
                current_question_id=qid,
                output_path=output_path,
            )
            trace_update = (
                lambda _trace, current_id=qid: self._refresh_dashboard(
                    enabled=True,
                    questions=questions,
                    current_question_id=current_id,
                    output_path=output_path,
                )
            ) if dashboard else None
            result = await self._run_one(
                question=public_question(question),
                question_dir=question_dir,
                title=title,
                description=description,
                on_trace_update=trace_update,
                timeout_seconds=question_timeout,
            )
            results[index - 1] = {
                "id": qid,
                "answer": str(result.get("answer", "")),
            }
            write_results(output_path, results)
            self._refresh_dashboard(
                enabled=dashboard,
                questions=questions,
                current_question_id=None,
                output_path=output_path,
            )
            trace = self._latest_trace(qid)
            self._print_event(
                "QUESTION_RESULT",
                self._question_diagnostics(
                    trace=trace,
                    result=results[index - 1],
                    index=index,
                    total=len(questions),
                    run_start=run_start,
                    output_path=output_path,
                ),
            )

        self._run_trace.total_duration_ms = int((time.monotonic() - run_start) * 1000)
        self._refresh_dashboard(
            enabled=dashboard,
            questions=questions,
            current_question_id=None,
            output_path=output_path,
        )

        self._print_event(
            "RUN_RESULT",
            {
                "status": "completed",
                "questions": len(questions),
                "results_written": len(questions),
                "answers_present": sum(
                    bool(str(item.get("answer", "")).strip())
                    for item in results
                ),
                **self._run_diagnostic_counts(),
                "cumulative_ms": self._elapsed_ms(run_start),
                "result_path": str(output_path),
                "result_bytes": self._file_size(output_path),
            },
        )
        return results

    def _refresh_dashboard(
        self,
        *,
        enabled: bool,
        questions: list[dict[str, Any]],
        current_question_id: str | None,
        output_path: Path,
    ) -> None:
        if not enabled:
            return

        dashboard_path = output_path.parent / "dashboard.html"
        trace_path = output_path.parent / "traces.json"
        try:
            from source.runtime.dashboard import write_dashboard

            self._run_trace.flush_to_file(trace_path)
            write_dashboard(
                output_path=dashboard_path,
                run_trace=self._run_trace,
                questions=questions,
                current_question_id=current_question_id,
                result_path=output_path,
                trace_path=trace_path,
            )
        except Exception as exc:
            print(f"dashboard refresh failed: {type(exc).__name__}: {exc}", file=sys.stderr)

    async def _run_one(
        self,
        *,
        question: dict[str, Any],
        question_dir: Path,
        title: str = "",
        description: str = "",
        on_trace_update: Callable[[QuestionTrace], None] | None = None,
        timeout_seconds: int | None = None,
    ) -> dict[str, Any]:
        qid = str(question.get("id", "unknown"))
        trace = begin_question_trace(
            qid,
            title=title,
            description=description,
            on_update=on_trace_update,
        )
        self._run_trace.add_question(trace)
        if on_trace_update is not None:
            on_trace_update(trace)
        try:
            with tempfile.TemporaryDirectory(prefix=f"agent_question_{qid}_") as temp_dir:
                context = self._build_context(
                    question=question,
                    question_dir=question_dir,
                    workspace_dir=Path(temp_dir),
                )
                solve = ContestantAgent().solve(question=question, context=context)
                if timeout_seconds is not None:
                    answer = await asyncio.wait_for(solve, timeout=timeout_seconds)
                else:
                    answer = await solve
            end_question_trace("success", str(answer))
            return {
                "id": qid,
                "answer": str(answer),
            }
        except asyncio.TimeoutError:
            message = f"question exceeded {timeout_seconds}s"
            print(f"question {qid} failed: {message}", file=sys.stderr)
            end_question_trace(
                "error",
                "",
                error=f"TimeoutError: {message}",
            )
            return {
                "id": qid,
                "answer": "",
            }
        except Exception as exc:
            print(f"question {qid} failed: {exc}", file=sys.stderr)
            end_question_trace(
                "error",
                "",
                error=f"{type(exc).__name__}: {exc}",
            )
            return {
                "id": qid,
                "answer": "",
            }

    def _build_context(
        self,
        *,
        question: dict[str, Any],
        question_dir: Path,
        workspace_dir: Path,
    ) -> AgentContext:
        files = question.get("files") or []
        allowed_file_paths = [
            question_dir.resolve(),
            *((question_dir / path).resolve() for path in files),
            workspace_dir.resolve(),
        ]
        return AgentContext(
            question=question,
            question_dir=question_dir,
            allowed_file_paths=allowed_file_paths,
            allowed_tools=self.mcp.tool_names(),
            allowed_agents=self.mcp.agent_names(),
            mcp=self.mcp,
            workspace_dir=workspace_dir.resolve(),
            package_id=self._config.package_id,
        )

    def _question_diagnostics(
        self,
        *,
        trace: QuestionTrace | None,
        result: dict[str, Any],
        index: int,
        total: int,
        run_start: float,
        output_path: Path,
    ) -> dict[str, Any]:
        answer = str(result.get("answer", ""))
        status = trace.status if trace is not None else "unknown"
        duration_ms = trace.duration_ms if trace is not None else 0
        counts = (
            trace.diagnostic_counts()
            if trace is not None
            else {"llm_calls": 0, "tool_calls": 0}
        )
        error_type, error_message = self._split_error(
            trace.error if trace is not None else None
        )
        return {
            "id": str(result.get("id", "")),
            "index": index,
            "total": total,
            "status": status,
            "answer_present": bool(answer.strip()),
            "answer_chars": len(answer),
            "duration_ms": duration_ms,
            "cumulative_ms": self._elapsed_ms(run_start),
            "llm_calls": counts["llm_calls"],
            "tool_calls": counts["tool_calls"],
            "results_written": index,
            "result_path": str(output_path),
            "result_bytes": self._file_size(output_path),
            "error_type": error_type,
            "error_message": error_message,
        }

    def _latest_trace(self, question_id: str) -> QuestionTrace | None:
        for trace in reversed(self._run_trace.questions):
            if trace.id == question_id:
                return trace
        return None

    def _run_diagnostic_counts(self) -> dict[str, int]:
        totals = {"llm_calls": 0, "tool_calls": 0}
        for trace in self._run_trace.questions:
            counts = trace.diagnostic_counts()
            totals["llm_calls"] += counts["llm_calls"]
            totals["tool_calls"] += counts["tool_calls"]
        return totals

    def _split_error(self, error: str | None) -> tuple[str | None, str | None]:
        if not error:
            return None, None
        error_type, separator, message = error.partition(":")
        if separator and error_type.strip():
            return error_type.strip(), message.lstrip()
        return "Error", error

    def _elapsed_ms(self, start: float) -> int:
        return int((time.monotonic() - start) * 1000)

    def _question_timeout_seconds(self) -> int:
        return max(1, env_int("AGENT_DEMO_QUESTION_TIMEOUT_SECONDS", QUESTION_TIMEOUT_SECONDS))

    def _file_size(self, path: Path) -> int:
        try:
            return path.stat().st_size
        except OSError:
            return 0

    def _print_event(self, name: str, payload: dict[str, Any]) -> None:
        print(
            f"[{name}] {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}",
            flush=True,
        )


def public_question(question: dict[str, Any]) -> dict[str, Any]:
    """Return the question object visible to the contestant Agent."""

    return public_question_fields(question)
