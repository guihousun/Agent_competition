from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from source.runtime.env_config import ModelConfig
from source.runtime.generate_dashboard import generate_dashboard
from source.solution import contestant_agent
from source.solution.sub_agents import _load_agent_package
from source.toolkits import main_mcp


ROOT = Path(__file__).resolve().parents[1]


class RuntimeBudgetTests(unittest.TestCase):
    def test_model_timeout_defaults_to_600_seconds(self) -> None:
        with (
            patch("source.runtime.env_config.load_dotenv"),
            patch.dict(os.environ, {}, clear=True),
        ):
            self.assertEqual(ModelConfig.from_env().timeout_seconds, 600)

    def test_model_stream_defaults_to_true(self) -> None:
        with (
            patch("source.runtime.env_config.load_dotenv"),
            patch.dict(os.environ, {}, clear=True),
        ):
            self.assertTrue(ModelConfig.from_env().stream)

    def test_model_timeout_and_stream_can_be_overridden(self) -> None:
        with (
            patch("source.runtime.env_config.load_dotenv"),
            patch.dict(
                os.environ,
                {
                    "AGENT_DEMO_TIMEOUT_SECONDS": "45",
                    "AGENT_DEMO_STREAM": "false",
                },
                clear=True,
            ),
        ):
            config = ModelConfig.from_env()

        self.assertEqual(config.timeout_seconds, 45)
        self.assertFalse(config.stream)

    def test_tool_output_limit_defaults_to_65536_chars(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(contestant_agent.tool_output_max_chars(), 65_536)


class DateComputeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        main_mcp.load_solution_skills()
        cls.date_compute = staticmethod(main_mcp.TOOLS["date_compute"].func)

    def result_for(self, expression: str, base_date: str = "") -> str:
        payload = json.loads(self.date_compute(expression=expression, base_date=base_date))
        return payload["result"]

    def test_longer_relative_day_is_matched_before_suffix(self) -> None:
        self.assertEqual(self.result_for("大后天", "2026-05-08"), "2026-05-11")

    def test_last_weekday_uses_previous_calendar_week(self) -> None:
        self.assertEqual(self.result_for("上周四", "2026-05-08"), "2026-04-30")

    def test_next_weekday_uses_next_calendar_week(self) -> None:
        self.assertEqual(self.result_for("下周二", "2026-05-11"), "2026-05-19")

    def test_hour_offset_preserves_time_before_returning_date(self) -> None:
        self.assertEqual(
            self.result_for("2026年5月6日23点开始算，100小时之后是哪一天"),
            "2026-05-11",
        )

    def test_days_after_does_not_fall_through_to_month_parsing(self) -> None:
        self.assertEqual(
            self.result_for("2026年5月6日下的单，选了3天后自提"),
            "2026-05-09",
        )

    def test_declared_fiscal_week_start_returns_friday_in_same_week(self) -> None:
        self.assertEqual(
            self.result_for("公司财年第2周从2026年1月5日开始，第2周的周五是几号"),
            "2026-01-09",
        )

    def test_known_next_week_anchor_does_not_replace_requested_weekday(self) -> None:
        self.assertEqual(
            self.result_for('自动邮件写"下周一是2026年5月11日"，帮我核实上周二是几号'),
            "2026-04-28",
        )

    def test_named_week_friday_works_with_declared_week_start_as_base(self) -> None:
        self.assertEqual(
            self.result_for("第2周的周五", "2026-01-05"),
            "2026-01-09",
        )

    def test_flexible_base_date_separator_is_accepted(self) -> None:
        self.assertEqual(
            self.result_for("3个自然日送达", "2026.12.21"),
            "2026-12-24",
        )

    def test_month_day_expression_uses_base_year(self) -> None:
        self.assertEqual(
            self.result_for("12月23日", "2026-12-21"),
            "2026-12-23",
        )


class LLMSubAgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_answer_checker_executes_llm_and_returns_verdict(self) -> None:
        agent = _load_agent_package(ROOT / "source/solution/agents/answer_checker")
        self.assertIsNotNone(agent)
        fake_client = AsyncMock()
        fake_client.create.return_value = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(
                            {
                                "overall_valid": False,
                                "cleaned_answer": "3",
                                "fix_suggestions": ["应为 2"],
                                "summary": "算术结果错误",
                            },
                            ensure_ascii=False,
                        ),
                    }
                }
            ]
        }

        with (
            patch(
                "source.solution.sub_agents.ChatCompletionClient",
                return_value=fake_client,
                create=True,
            ),
            patch("source.solution.sub_agents.ModelConfig", create=True),
        ):
            result = await agent.run(
                task="3",
                context_text="计算结果应为 2",
                runtime_context={
                    "question": {"id": "math", "question": "1+1 等于多少？"},
                    "allowed_file_paths": [],
                },
                tools=[
                    {
                        "type": "function",
                        "function": {
                            "name": "code_execute",
                            "description": "execute",
                            "parameters": {"type": "object", "properties": {}},
                        },
                    },
                    {
                        "type": "function",
                        "function": {
                            "name": "http_request",
                            "description": "network",
                            "parameters": {"type": "object", "properties": {}},
                        },
                    },
                ],
                tool_runner=AsyncMock(),
            )

        self.assertFalse(json.loads(result)["overall_valid"])
        fake_client.create.assert_awaited_once()
        user_payload = json.loads(
            fake_client.create.await_args.kwargs["messages"][1]["content"]
        )
        self.assertEqual(user_payload["question_description"], "1+1 等于多少？")
        self.assertEqual(fake_client.create.await_args.kwargs["tool_choice"], "required")
        checker_tool_names = {
            item["function"]["name"]
            for item in fake_client.create.await_args.kwargs["tools"]
        }
        self.assertEqual(checker_tool_names, {"code_execute"})

    async def test_data_reader_can_call_allowed_tool_before_returning_json(self) -> None:
        agent = _load_agent_package(ROOT / "source/solution/agents/data_reader")
        self.assertIsNotNone(agent)
        fake_client = AsyncMock()
        fake_client.create.side_effect = [
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "read_1",
                                    "type": "function",
                                    "function": {
                                        "name": "text_read_file",
                                        "arguments": json.dumps({"path": "data.csv"}),
                                    },
                                }
                            ],
                        }
                    }
                ]
            },
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(
                                {
                                    "mode": "overview",
                                    "files_read": ["data.csv"],
                                    "data_landscape": {"data.csv": {"rows": 2}},
                                }
                            ),
                        }
                    }
                ]
            },
        ]
        tool_runner = AsyncMock(return_value="name,value\nA,1\nB,2\n")
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "text_read_file",
                    "description": "read",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]

        with (
            patch(
                "source.solution.sub_agents.ChatCompletionClient",
                return_value=fake_client,
                create=True,
            ),
            patch("source.solution.sub_agents.ModelConfig", create=True),
        ):
            result = await agent.run(
                task="探查数据结构",
                context_text="data.csv",
                runtime_context={
                    "question": {
                        "id": "data",
                        "description": "读取数据",
                        "files": ["data.csv"],
                    },
                    "allowed_file_paths": [str(ROOT / "data.csv")],
                },
                tools=tools,
                tool_runner=tool_runner,
            )

        self.assertEqual(json.loads(result)["mode"], "overview")
        tool_runner.assert_awaited_once_with("text_read_file", {"path": "data.csv"})
        self.assertEqual(fake_client.create.await_count, 2)

    async def test_verifier_uses_corrected_answer_before_main_model_rewrite(self) -> None:
        checker_results = [
            {
                "overall_valid": False,
                "cleaned_answer": "3",
                "corrected_answer": "2",
                "fix_suggestions": ["重新计算算术结果"],
                "summary": "候选答案错误",
            },
            {
                "overall_valid": True,
                "cleaned_answer": "2",
                "corrected_answer": "2",
                "fix_suggestions": [],
                "summary": "验证通过",
            },
        ]
        context = SimpleNamespace()
        context.call_tool = AsyncMock(
            side_effect=[json.dumps(item, ensure_ascii=False) for item in checker_results]
        )
        client = AsyncMock()

        result = await contestant_agent.ContestantAgent()._verify_and_fix(
            candidate="3",
            messages=[
                {"role": "system", "content": "system"},
                {"role": "user", "content": "1+1 等于多少？"},
            ],
            client=client,
            tools=[],
            context=context,
        )

        self.assertEqual(result, "2")
        self.assertEqual(context.call_tool.await_count, 2)
        client.create.assert_not_awaited()

    async def test_verifier_preserves_candidate_after_repeated_invalid_json(self) -> None:
        context = SimpleNamespace()
        context.call_tool = AsyncMock(side_effect=["not-json", "still-not-json"])

        result = await contestant_agent.ContestantAgent()._verify_and_fix(
            candidate="candidate-answer",
            messages=[
                {"role": "system", "content": "system"},
                {"role": "user", "content": "question"},
            ],
            client=AsyncMock(),
            tools=[],
            context=context,
        )

        self.assertEqual(result, "candidate-answer")
        self.assertEqual(context.call_tool.await_count, 2)

    def test_sub_agent_prompt_builder_uses_utf8_for_bom_context(self) -> None:
        agent = _load_agent_package(ROOT / "source/solution/agents/answer_checker")
        self.assertIsNotNone(agent)

        prompt_package = agent._build_prompt_package(
            "candidate",
            "\ufeffevidence",
            {"question": {"id": "utf8", "question": "verify"}},
        )

        self.assertEqual(prompt_package["context"], "\ufeffevidence")


class DashboardSemanticsTests(unittest.TestCase):
    def test_dashboard_labels_execution_status_without_claiming_correctness(self) -> None:
        traces = {
            "run_id": "run-test",
            "model": "test-model",
            "start_time": "2026-06-12T00:00:00+00:00",
            "total_duration_ms": 1,
            "questions": [
                {
                    "id": "q1",
                    "status": "success",
                    "answer": "possibly wrong",
                    "error": None,
                    "duration_ms": 1,
                    "tokens": {"prompt": 0, "completion": 0},
                    "spans": [],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            traces_path = Path(temp_dir) / "traces.json"
            output_path = Path(temp_dir) / "dashboard.html"
            traces_path.write_text(json.dumps(traces), encoding="utf-8")
            generate_dashboard(traces_path, output_path)
            html = output_path.read_text(encoding="utf-8")

        self.assertIn('<div class="label">Completed</div>', html)
        self.assertIn('<div class="label">Errors</div>', html)
        self.assertNotIn('<div class="label">Passed</div>', html)


if __name__ == "__main__":
    unittest.main()
