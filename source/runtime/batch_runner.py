from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import time
from typing import Any

from source.runtime.agent_context import AgentContext
from source.runtime.agent_registry import AgentRegistry
from source.runtime.mcp_client import LocalMCPClient
from source.runtime.question_loader import load_questions
from source.runtime.question_schema import public_question_fields
from source.runtime.result_writer import write_results
from source.runtime.tracing import (
    RunTrace,
    begin_question_trace,
    create_run_trace,
    end_question_trace,
    get_active_trace,
)
from source.runtime.env_config import ModelConfig, load_dotenv
from source.solution.contestant_agent import ContestantAgent


class BatchRunner:
    def __init__(self) -> None:
        self.mcp = LocalMCPClient(agent_registry=AgentRegistry())
        load_dotenv()
        self._config = ModelConfig.from_env()
        self._run_trace = create_run_trace(model=self._config.model)

    async def run_file(self, *, question_path: str | Path, output_path: str | Path) -> list[dict[str, Any]]:
        question_path = Path(question_path).resolve()
        output_path = Path(output_path).resolve()
        questions = load_questions(question_path)
        question_dir = question_path.parent
        results: list[dict[str, Any]] = []
        run_start = time.monotonic()

        for index, question in enumerate(questions, start=1):
            qid = str(question.get("id", index))
            print(f"[{index}/{len(questions)}] running question {qid}")
            result = await self._run_one(question=public_question(question), question_dir=question_dir)
            results.append(result)
            write_results(output_path, results)

        self._run_trace.total_duration_ms = int((time.monotonic() - run_start) * 1000)

        # Write traces and generate dashboard alongside results
        traces_path = output_path.with_name("traces.json")
        self._run_trace.flush_to_file(traces_path)
        print(f"traces saved to: {traces_path}")

        try:
            from source.runtime.generate_dashboard import generate_dashboard
            dashboard_path = output_path.with_name("dashboard.html")
            generate_dashboard(traces_path, dashboard_path)
            print(f"dashboard saved to: {dashboard_path}")
        except Exception as exc:
            print(f"dashboard generation skipped: {exc}", file=sys.stderr)

        return results

    async def _run_one(self, *, question: dict[str, Any], question_dir: Path) -> dict[str, Any]:
        qid = str(question.get("id", "unknown"))
        trace = begin_question_trace(qid)
        try:
            with tempfile.TemporaryDirectory(prefix=f"agent_question_{qid}_") as temp_dir:
                context = self._build_context(
                    question=question,
                    question_dir=question_dir,
                    workspace_dir=Path(temp_dir),
                )
                answer = await ContestantAgent().solve(question=question, context=context)
            end_question_trace("success", str(answer))
            self._run_trace.add_question(trace)
            return {
                "id": qid,
                "answer": str(answer),
            }
        except Exception as exc:
            print(f"question {qid} failed: {exc}", file=sys.stderr)
            end_question_trace("error", "", error=str(exc))
            self._run_trace.add_question(trace)
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


def public_question(question: dict[str, Any]) -> dict[str, Any]:
    """Return the question object visible to the contestant Agent."""

    return public_question_fields(question)
