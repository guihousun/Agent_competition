from __future__ import annotations

import asyncio
import io
import json
import subprocess
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

from source.runtime.agent_registry import AgentRegistry
from source.runtime.mcp_client import LocalMCPClient
from source.solution.contestant_agent import ContestantAgent
from source.toolkits import main_mcp


class NativeFallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_generic_failure_does_not_replay_task_in_json_mode(self) -> None:
        agent = ContestantAgent()
        agent._run_native_tool_loop = AsyncMock(side_effect=RuntimeError("tool side effect failed"))
        agent._run_json_tool_loop = AsyncMock(return_value="replayed")

        with patch.dict(
            "os.environ",
            {
                "AGENT_DEMO_NATIVE_TOOLS": "true",
                "AGENT_DEMO_JSON_TOOL_FALLBACK": "true",
            },
            clear=False,
        ):
            with self.assertRaisesRegex(RuntimeError, "tool side effect failed"):
                await agent._run_model_loop(
                    system_prompt="system",
                    user_prompt="user",
                    context=AsyncMock(),
                )

        agent._run_json_tool_loop.assert_not_awaited()

    async def test_explicit_unsupported_tools_error_uses_json_fallback(self) -> None:
        agent = ContestantAgent()
        agent._run_native_tool_loop = AsyncMock(
            side_effect=RuntimeError(
                "Model gateway HTTP 400: unsupported parameter: tools"
            )
        )
        agent._run_json_tool_loop = AsyncMock(return_value="fallback-result")

        with patch.dict(
            "os.environ",
            {
                "AGENT_DEMO_NATIVE_TOOLS": "true",
                "AGENT_DEMO_JSON_TOOL_FALLBACK": "true",
            },
            clear=False,
        ):
            result = await agent._run_model_loop(
                system_prompt="system",
                user_prompt="user",
                context=AsyncMock(),
            )

        self.assertEqual(result, "fallback-result")
        agent._run_json_tool_loop.assert_awaited_once()


class JavaExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        main_mcp.load_solution_skills()
        cls.code_execute = staticmethod(main_mcp.TOOLS["code_execute"].func)

    def test_public_class_uses_correct_filename_utf8_and_args(self) -> None:
        code = """
public class Main {
    public static void main(String[] args) {
        System.out.print("中文:" + String.join("|", args));
    }
}
""".strip()
        result = json.loads(
            self.code_execute(
                language="java",
                code=code,
                args=["甲", "乙"],
                timeout=30,
            )
        )

        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["stdout"], "中文:甲|乙")

    def test_java_compiles_once_and_runs_multiple_stdin_cases(self) -> None:
        code = """
import java.util.Scanner;
public class Main {
    public static void main(String[] args) {
        Scanner scanner = new Scanner(System.in);
        int value = scanner.nextInt();
        System.out.print(value * 2);
    }
}
""".strip()
        result = json.loads(
            self.code_execute(
                language="java",
                code=code,
                stdin_cases=["2\n", "7\n"],
                timeout=30,
            )
        )

        self.assertEqual(
            [run["stdout"] for run in result["runs"]],
            ["4", "14"],
        )
        self.assertTrue(all(run["exit_code"] == 0 for run in result["runs"]))

    def test_java_timeout_returns_structured_error(self) -> None:
        with patch(
            "source.solution.mcp.contestant_tools.subprocess.run",
            side_effect=subprocess.TimeoutExpired(["javac"], 1),
        ):
            result = json.loads(
                self.code_execute(
                    language="java",
                    code="public class Main { public static void main(String[] args) {} }",
                    timeout=1,
                )
            )

        self.assertEqual(result["exit_code"], -1)
        self.assertEqual(result["error"], "timeout")


class ArchiveWorkspaceTests(unittest.IsolatedAsyncioTestCase):
    async def test_zip_output_is_readable_through_same_runtime_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive_path = root / "input.zip"
            workspace = root / "workspace"
            workspace.mkdir()
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("nested/data.txt", "archive-ok")

            mcp = LocalMCPClient(agent_registry=AgentRegistry())
            runtime = self._runtime(
                root=root,
                workspace=workspace,
                archive_path=archive_path,
                mcp=mcp,
            )
            extracted = json.loads(
                await mcp.call_tool(
                    "zip_extract",
                    {"zip_path": str(archive_path)},
                    runtime_context=runtime,
                )
            )
            content = await mcp.call_tool(
                "text_read_file",
                {"path": extracted["files"][0]},
                runtime_context=runtime,
            )

        self.assertEqual(content, "archive-ok")
        self.assertTrue(Path(extracted["output_dir"]).is_relative_to(workspace))

    async def test_tar_output_is_readable_through_same_runtime_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive_path = root / "input.tar"
            workspace = root / "workspace"
            workspace.mkdir()
            payload = b"tar-ok"
            with tarfile.open(archive_path, "w") as archive:
                info = tarfile.TarInfo("nested/data.txt")
                info.size = len(payload)
                archive.addfile(info, io.BytesIO(payload))

            mcp = LocalMCPClient(agent_registry=AgentRegistry())
            runtime = self._runtime(
                root=root,
                workspace=workspace,
                archive_path=archive_path,
                mcp=mcp,
            )
            extracted = json.loads(
                await mcp.call_tool(
                    "tar_extract",
                    {"tar_path": str(archive_path)},
                    runtime_context=runtime,
                )
            )
            content = await mcp.call_tool(
                "text_read_file",
                {"path": extracted["files"][0]},
                runtime_context=runtime,
            )

        self.assertEqual(content, "tar-ok")

    async def test_zip_traversal_member_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive_path = root / "unsafe.zip"
            workspace = root / "workspace"
            workspace.mkdir()
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("../escape.txt", "escape")

            mcp = LocalMCPClient(agent_registry=AgentRegistry())
            runtime = self._runtime(
                root=root,
                workspace=workspace,
                archive_path=archive_path,
                mcp=mcp,
            )
            result = json.loads(
                await mcp.call_tool(
                    "zip_extract",
                    {"zip_path": str(archive_path)},
                    runtime_context=runtime,
                )
            )

        self.assertIn("unsafe archive member", result["error"].lower())
        self.assertFalse((root / "escape.txt").exists())

    async def test_basename_resolves_inside_declared_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            declared_dir = root / "declared"
            declared_dir.mkdir()
            expected = declared_dir / "data.csv"
            expected.write_text("value\n1\n", encoding="utf-8")
            workspace = root / "workspace"
            workspace.mkdir()
            mcp = LocalMCPClient(agent_registry=AgentRegistry())
            runtime = {
                "question_id": "directory",
                "question": {"id": "directory", "question": "read"},
                "question_dir": str(root),
                "workspace_dir": str(workspace),
                "allowed_file_paths": [str(declared_dir), str(workspace)],
                "allowed_tools": mcp.tool_names(),
                "allowed_agents": [],
                "package_id": "",
            }

            content = await mcp.call_tool(
                "text_read_file",
                {"path": "data.csv"},
                runtime_context=runtime,
            )

        self.assertEqual(content, "value\n1\n")

    def _runtime(
        self,
        *,
        root: Path,
        workspace: Path,
        archive_path: Path,
        mcp: LocalMCPClient,
    ) -> dict:
        return {
            "question_id": "archive",
            "question": {"id": "archive", "question": "extract"},
            "question_dir": str(root),
            "workspace_dir": str(workspace),
            "allowed_file_paths": [str(archive_path), str(workspace)],
            "allowed_tools": mcp.tool_names(),
            "allowed_agents": [],
            "package_id": "",
        }


class PackageHeaderTests(unittest.IsolatedAsyncioTestCase):
    async def test_package_header_is_injected_when_missing(self) -> None:
        request_holder = {}

        class FakeResponse:
            status = 200
            headers = {}

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return b"{}"

        def fake_urlopen(request, timeout):
            request_holder["request"] = request
            return FakeResponse()

        mcp = LocalMCPClient(agent_registry=AgentRegistry())
        runtime = self._http_runtime(mcp, package_id="pkg-123")
        with patch(
            "source.solution.mcp.contestant_tools.urllib.request.urlopen",
            side_effect=fake_urlopen,
        ):
            await mcp.call_tool(
                "http_request",
                {"url": "http://example.test"},
                runtime_context=runtime,
            )

        self.assertEqual(
            request_holder["request"].headers["X-package-id"],
            "pkg-123",
        )

    async def test_explicit_package_header_takes_precedence(self) -> None:
        request_holder = {}

        class FakeResponse:
            status = 200
            headers = {}

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return b"{}"

        def fake_urlopen(request, timeout):
            request_holder["request"] = request
            return FakeResponse()

        mcp = LocalMCPClient(agent_registry=AgentRegistry())
        runtime = self._http_runtime(mcp, package_id="runtime-value")
        with patch(
            "source.solution.mcp.contestant_tools.urllib.request.urlopen",
            side_effect=fake_urlopen,
        ):
            await mcp.call_tool(
                "http_request",
                {
                    "url": "http://example.test",
                    "headers": {"x-package-id": "explicit-value"},
                },
                runtime_context=runtime,
            )

        self.assertEqual(
            request_holder["request"].headers["X-package-id"],
            "explicit-value",
        )

    def _http_runtime(self, mcp: LocalMCPClient, package_id: str) -> dict:
        return {
            "question_id": "http",
            "question": {"id": "http", "question": "request"},
            "question_dir": str(Path.cwd()),
            "workspace_dir": str(Path.cwd()),
            "allowed_file_paths": [],
            "allowed_tools": mcp.tool_names(),
            "allowed_agents": [],
            "package_id": package_id,
        }


if __name__ == "__main__":
    unittest.main()
