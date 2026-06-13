from __future__ import annotations

import csv
import io
import json
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Callable

from source.solution.mcp.api_test_executor import execute_api_test_plan
from source.solution.mcp.evidence_chain import analyze_evidence_chain


def _safe_archive_target(output_root: Path, member_name: str) -> Path:
    normalized = member_name.replace("\\", "/")
    relative = Path(normalized)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"Unsafe archive member: {member_name}")
    target = (output_root / relative).resolve()
    if target == output_root or not target.is_relative_to(output_root):
        raise ValueError(f"Unsafe archive member: {member_name}")
    return target


def _java_main_class_name(code: str) -> str | None:
    public_match = re.search(
        r"\bpublic\s+(?:(?:final|abstract|strictfp)\s+)*class\s+([A-Za-z_$][\w$]*)",
        code,
    )
    if public_match:
        return public_match.group(1)

    for class_match in re.finditer(
        r"\bclass\s+([A-Za-z_$][\w$]*)",
        code,
    ):
        class_body = code[class_match.end():]
        if re.search(r"\bstatic\s+(?:public\s+)?void\s+main\s*\(", class_body):
            return class_match.group(1)
        if re.search(r"\bpublic\s+static\s+void\s+main\s*\(", class_body):
            return class_match.group(1)
    return None


def register_tools(*, register_tool: Callable[..., Callable], object_schema: Callable[..., dict[str, Any]]) -> None:
    """Register contestant MCP-style tools.

    This file is loaded by source/toolkits/main_mcp.py. Contestants can add,
    remove, or replace tools here when a capability is better exposed as a
    direct MCP-style function than as a SKILL.md package.
    """

    @register_tool(
        name="mock_order_lookup",
        description="Mock MCP-style tool. Returns a fixed mock order lookup result for demo purposes.",
        input_schema=object_schema(
            {
                "order_id": {
                    "type": "string",
                    "description": "Mock order id, for example MOCK-1001.",
                }
            },
            ["order_id"],
        ),
        kind="mcp",
        risk="low",
    )
    def mock_order_lookup(order_id: str) -> str:
        return json.dumps(
            {
                "mock_result": "mock-order-lookup-ok",
                "source": "mock_mcp",
                "order_id": order_id,
            },
            ensure_ascii=False,
            indent=2,
        )

    @register_tool(
        name="mock_policy_check",
        description="Mock MCP-style tool. Returns a fixed mock policy check result for demo purposes.",
        input_schema=object_schema(
            {
                "payload": {
                    "type": "string",
                    "description": "Mock payload to check.",
                }
            },
            ["payload"],
        ),
        kind="mcp",
        risk="low",
    )
    def mock_policy_check(payload: str) -> str:
        return json.dumps(
            {
                "mock_result": "mock-policy-check-ok",
                "source": "mock_mcp",
                "payload_preview": payload[:80],
            },
            ensure_ascii=False,
            indent=2,
        )

    # =========================================================================
    # P0 Competition Tools
    # =========================================================================

    @register_tool(
        name="evidence_chain_analyze",
        description=(
            "Parse frontend/backend logs, HAR files, screenshots, and a validation "
            "schema; correlate complete foreground failure flows and map root causes."
        ),
        input_schema=object_schema(
            {
                "frontend_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": [],
                },
                "backend_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": [],
                },
                "har_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": [],
                },
                "schema_path": {"type": "string"},
                "screenshot_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": [],
                },
            },
            ["schema_path"],
        ),
        kind="mcp",
        risk="medium",
    )
    def evidence_chain_analyze(
        frontend_paths: list[str] | None = None,
        backend_paths: list[str] | None = None,
        har_paths: list[str] | None = None,
        schema_path: str = "",
        screenshot_paths: list[str] | None = None,
    ) -> str:
        return json.dumps(
            analyze_evidence_chain(
                frontend_paths=frontend_paths,
                backend_paths=backend_paths,
                har_paths=har_paths,
                schema_path=schema_path,
                screenshot_paths=screenshot_paths,
            ),
            ensure_ascii=False,
            indent=2,
        )

    @register_tool(
        name="api_test_execute",
        description=(
            "Validate and sequentially execute a complete HTTP API test plan. "
            "Supports response variable extraction and deterministic JSON assertions."
        ),
        input_schema=object_schema(
            {
                "plan": {
                    "type": "object",
                    "description": (
                        "Execution plan with base_url and ordered cases/steps. "
                        "Each case may contain assert/expectedStatus/expectedFields/"
                        "expectedValues; steps may extract variables by JSON path."
                    ),
                    "additionalProperties": True,
                }
            },
            ["plan"],
        ),
        kind="mcp",
        risk="high",
    )
    def api_test_execute(
        plan: dict[str, Any],
        package_id: str = "",
        auth_config: dict[str, Any] | None = None,
    ) -> str:
        return json.dumps(
            execute_api_test_plan(
                plan=plan,
                package_id=package_id,
                auth_config=auth_config,
            ),
            ensure_ascii=False,
            indent=2,
        )

    @register_tool(
        name="http_request",
        description="Send HTTP request and return response. Supports GET/POST/PUT/DELETE with custom headers and body.",
        input_schema=object_schema(
            {
                "url": {
                    "type": "string",
                    "description": "Target URL (e.g., http://localhost:18080/api/question)",
                },
                "method": {
                    "type": "string",
                    "description": "HTTP method: GET, POST, PUT, DELETE, PATCH",
                    "default": "GET",
                },
                "headers": {
                    "type": "object",
                    "description": "Request headers as key-value pairs",
                    "default": {},
                },
                "body": {
                    "type": "string",
                    "description": "Request body (for POST/PUT/PATCH)",
                    "default": "",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds",
                    "default": 30,
                },
            },
            ["url"],
        ),
        kind="mcp",
        risk="medium",
    )
    def http_request(
        url: str,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        body: str = "",
        timeout: int = 30,
    ) -> str:
        """Send HTTP request and return response status + body."""
        headers = headers or {}
        method = method.upper()

        try:
            req = urllib.request.Request(url, method=method)
            for key, value in headers.items():
                req.add_header(key, value)

            if body and method in ("POST", "PUT", "PATCH"):
                if isinstance(body, str):
                    body = body.encode("utf-8")
                req.data = body

            with urllib.request.urlopen(req, timeout=timeout) as response:
                status = response.status
                response_headers = dict(response.headers)
                response_body = response.read().decode("utf-8", errors="replace")

            return json.dumps(
                {
                    "status": status,
                    "headers": response_headers,
                    "body": response_body[:50000],
                    "success": 200 <= status < 300,
                },
                ensure_ascii=False,
                indent=2,
            )
        except urllib.error.HTTPError as exc:
            return json.dumps(
                {
                    "status": exc.code,
                    "error": str(exc.reason),
                    "body": exc.read().decode("utf-8", errors="replace")[:10000],
                    "success": False,
                },
                ensure_ascii=False,
                indent=2,
            )
        except urllib.error.URLError as exc:
            return json.dumps(
                {
                    "status": 0,
                    "error": str(exc.reason),
                    "success": False,
                },
                ensure_ascii=False,
                indent=2,
            )
        except Exception as exc:
            return json.dumps(
                {
                    "status": -1,
                    "error": str(exc),
                    "success": False,
                },
                ensure_ascii=False,
                indent=2,
            )

    @register_tool(
        name="zip_extract",
        description="Extract ZIP file contents. Returns list of extracted files.",
        input_schema=object_schema(
            {
                "zip_path": {
                    "type": "string",
                    "description": "Path to ZIP file",
                },
                "output_dir": {
                    "type": "string",
                    "description": "Output directory (default: temp directory)",
                    "default": "",
                },
            },
            ["zip_path"],
        ),
        kind="mcp",
        risk="medium",
    )
    def zip_extract(zip_path: str, output_dir: str = "") -> str:
        """Extract ZIP file and return list of extracted files."""
        zip_path = Path(zip_path)
        if not zip_path.exists():
            return json.dumps({"error": f"ZIP file not found: {zip_path}"}, ensure_ascii=False)

        if not output_dir:
            output_dir = tempfile.mkdtemp(prefix="zip_extract_")
        else:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)

        extracted = []
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                output_root = Path(output_dir).resolve()
                for member in zf.infolist():
                    target = _safe_archive_target(output_root, member.filename)
                    mode = member.external_attr >> 16
                    if stat.S_ISLNK(mode):
                        raise ValueError(f"Unsafe archive member (link): {member.filename}")
                    if member.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member, "r") as source, target.open("wb") as destination:
                        shutil.copyfileobj(source, destination)
                    extracted.append(str(target))
        except zipfile.BadZipFile:
            return json.dumps({"error": f"Invalid ZIP file: {zip_path}"}, ensure_ascii=False)
        except Exception as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)

        return json.dumps(
            {
                "output_dir": str(output_dir),
                "files": extracted,
                "count": len(extracted),
            },
            ensure_ascii=False,
            indent=2,
        )

    @register_tool(
        name="tar_extract",
        description="Extract TAR/TAR.GZ/TAR.BZ2 file contents. Returns list of extracted files. Supports .tar, .tar.gz, .tgz, .tar.bz2 formats.",
        input_schema=object_schema(
            {
                "tar_path": {
                    "type": "string",
                    "description": "Path to TAR file (.tar, .tar.gz, .tgz, .tar.bz2)",
                },
                "output_dir": {
                    "type": "string",
                    "description": "Output directory (default: temp directory)",
                    "default": "",
                },
            },
            ["tar_path"],
        ),
        kind="mcp",
        risk="medium",
    )
    def tar_extract(tar_path: str, output_dir: str = "") -> str:
        """Extract TAR file and return list of extracted files."""
        tar_path = Path(tar_path)
        if not tar_path.exists():
            return json.dumps({"error": f"TAR file not found: {tar_path}"}, ensure_ascii=False)

        if not output_dir:
            output_dir = tempfile.mkdtemp(prefix="tar_extract_")
        else:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)

        extracted = []
        try:
            with tarfile.open(tar_path, "r:*") as tf:
                output_root = Path(output_dir).resolve()
                for member in tf.getmembers():
                    target = _safe_archive_target(output_root, member.name)
                    if member.issym() or member.islnk() or member.isdev():
                        raise ValueError(f"Unsafe archive member (link/device): {member.name}")
                    if member.isdir():
                        target.mkdir(parents=True, exist_ok=True)
                        continue
                    if not member.isfile():
                        raise ValueError(f"Unsafe archive member type: {member.name}")
                    source = tf.extractfile(member)
                    if source is None:
                        raise ValueError(f"Could not read archive member: {member.name}")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with source, target.open("wb") as destination:
                        shutil.copyfileobj(source, destination)
                    extracted.append(str(target))
        except tarfile.TarError as exc:
            return json.dumps({"error": f"Invalid TAR file: {exc}"}, ensure_ascii=False)
        except Exception as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)

        return json.dumps(
            {
                "output_dir": str(output_dir),
                "files": extracted,
                "count": len(extracted),
            },
            ensure_ascii=False,
            indent=2,
        )

    @register_tool(
        name="csv_read",
        description="Read CSV file and return as JSON array. Supports custom delimiter and encoding.",
        input_schema=object_schema(
            {
                "path": {
                    "type": "string",
                    "description": "Path to CSV file",
                },
                "delimiter": {
                    "type": "string",
                    "description": "Column delimiter",
                    "default": ",",
                },
                "encoding": {
                    "type": "string",
                    "description": "File encoding",
                    "default": "utf-8",
                },
                "max_rows": {
                    "type": "integer",
                    "description": "Maximum rows to read (0 = all)",
                    "default": 0,
                },
            },
            ["path"],
        ),
        kind="mcp",
        risk="low",
    )
    def csv_read(
        path: str,
        delimiter: str = ",",
        encoding: str = "utf-8",
        max_rows: int = 0,
    ) -> str:
        """Read CSV file and return JSON array."""
        path = Path(path)
        if not path.exists():
            return json.dumps({"error": f"File not found: {path}"}, ensure_ascii=False)

        rows = []
        try:
            with path.open("r", encoding=encoding, newline="") as f:
                reader = csv.DictReader(f, delimiter=delimiter)
                for i, row in enumerate(reader):
                    if max_rows > 0 and i >= max_rows:
                        break
                    rows.append(row)
        except Exception as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)

        return json.dumps(
            {
                "path": str(path),
                "rows": len(rows),
                "columns": list(rows[0].keys()) if rows else [],
                "data": rows[:1000],
            },
            ensure_ascii=False,
            indent=2,
        )

    @register_tool(
        name="csv_aggregate",
        description="Aggregate CSV data: SUM/AVG/COUNT/MIN/MAX with optional GROUP BY.",
        input_schema=object_schema(
            {
                "data": {
                    "type": "array",
                    "description": "CSV rows as JSON array (from csv_read)",
                },
                "operation": {
                    "type": "string",
                    "description": "Aggregation: SUM, AVG, COUNT, MIN, MAX",
                },
                "column": {
                    "type": "string",
                    "description": "Target column name",
                },
                "group_by": {
                    "type": "string",
                    "description": "Group by column (optional)",
                    "default": "",
                },
            },
            ["data", "operation", "column"],
        ),
        kind="mcp",
        risk="low",
    )
    def csv_aggregate(
        data: list[dict[str, Any]],
        operation: str,
        column: str,
        group_by: str = "",
    ) -> str:
        """Aggregate CSV data."""
        if not data:
            return json.dumps({"error": "Empty data"}, ensure_ascii=False)

        operation = operation.upper()
        values = []
        for row in data:
            try:
                val = float(row.get(column, 0))
                values.append(val)
            except (ValueError, TypeError):
                pass

        if not values:
            return json.dumps({"error": f"No numeric values in column: {column}"}, ensure_ascii=False)

        if operation == "SUM":
            result = sum(values)
        elif operation == "AVG":
            result = sum(values) / len(values)
        elif operation == "COUNT":
            result = len(values)
        elif operation == "MIN":
            result = min(values)
        elif operation == "MAX":
            result = max(values)
        else:
            return json.dumps({"error": f"Unknown operation: {operation}"}, ensure_ascii=False)

        return json.dumps(
            {
                "operation": operation,
                "column": column,
                "result": result,
                "count": len(values),
            },
            ensure_ascii=False,
            indent=2,
        )

    @register_tool(
        name="code_execute",
        description="Execute code (Python/Java/Node.js) and return stdout/stderr/exit_code.",
        input_schema=object_schema(
            {
                "language": {
                    "type": "string",
                    "description": "Programming language: python, java, node",
                },
                "code": {
                    "type": "string",
                    "description": "Source code to execute",
                },
                "stdin": {
                    "type": "string",
                    "description": "Standard input",
                    "default": "",
                },
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Command-line arguments passed to the program",
                    "default": [],
                },
                "stdin_cases": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional multiple stdin cases. Java is compiled once and run once per case.",
                    "default": [],
                },
                "timeout": {
                    "type": "integer",
                    "description": "Execution timeout in seconds",
                    "default": 30,
                },
            },
            ["language", "code"],
        ),
        kind="mcp",
        risk="high",
    )
    def code_execute(
        language: str,
        code: str,
        stdin: str = "",
        args: list[str] | None = None,
        stdin_cases: list[str] | None = None,
        timeout: int = 30,
    ) -> str:
        """Execute code and return output."""
        language = language.lower()
        args = [str(value) for value in (args or [])]
        stdin_cases = [str(value) for value in (stdin_cases or [])]

        if language == "python":
            cmd = [sys.executable, "-c", code, *args]
        elif language == "java":
            class_name = _java_main_class_name(code)
            if not class_name:
                return json.dumps(
                    {
                        "language": language,
                        "exit_code": -1,
                        "stdout": "",
                        "stderr": "Could not identify a Java class containing main().",
                        "error": "main class not found",
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            try:
                with tempfile.TemporaryDirectory(prefix="java_execute_") as temp_dir:
                    java_file = Path(temp_dir) / f"{class_name}.java"
                    java_file.write_text(code, encoding="utf-8")
                    compile_result = subprocess.run(
                        ["javac", "-encoding", "UTF-8", java_file.name],
                        cwd=temp_dir,
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=timeout,
                    )
                    if compile_result.returncode != 0:
                        return json.dumps(
                            {
                                "language": language,
                                "exit_code": -1,
                                "stdout": "",
                                "stderr": compile_result.stderr,
                                "error": "Compilation failed",
                            },
                            ensure_ascii=False,
                            indent=2,
                        )
                    cases = stdin_cases if stdin_cases else [stdin]
                    runs = []
                    java_cmd = [
                        "java",
                        "-Dfile.encoding=UTF-8",
                        "-Dsun.stdout.encoding=UTF-8",
                        "-Dsun.stderr.encoding=UTF-8",
                        "-cp",
                        temp_dir,
                        class_name,
                        *args,
                    ]
                    for index, case_stdin in enumerate(cases):
                        run_result = subprocess.run(
                            java_cmd,
                            input=case_stdin,
                            capture_output=True,
                            text=True,
                            encoding="utf-8",
                            errors="replace",
                            timeout=timeout,
                        )
                        runs.append(
                            {
                                "index": index,
                                "stdin": case_stdin,
                                "args": args,
                                "exit_code": run_result.returncode,
                                "stdout": run_result.stdout[:50000],
                                "stderr": run_result.stderr[:10000],
                            }
                        )
                    if stdin_cases:
                        return json.dumps(
                            {
                                "language": language,
                                "class_name": class_name,
                                "compile_exit_code": compile_result.returncode,
                                "runs": runs,
                            },
                            ensure_ascii=False,
                            indent=2,
                        )
                    run_result = runs[0]
                    return json.dumps(
                        {
                            "language": language,
                            "class_name": class_name,
                            "exit_code": run_result["exit_code"],
                            "stdout": run_result["stdout"],
                            "stderr": run_result["stderr"],
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
            except subprocess.TimeoutExpired:
                return json.dumps(
                    {
                        "language": language,
                        "exit_code": -1,
                        "stdout": "",
                        "stderr": f"Execution timeout after {timeout}s",
                        "error": "timeout",
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            except Exception as exc:
                return json.dumps(
                    {
                        "language": language,
                        "exit_code": -1,
                        "stdout": "",
                        "stderr": str(exc),
                        "error": str(exc),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
        elif language == "node":
            cmd = ["node", "-e", code, *args]
        else:
            return json.dumps({"error": f"Unsupported language: {language}"}, ensure_ascii=False)

        try:
            result = subprocess.run(
                cmd,
                input=stdin,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return json.dumps(
                {
                    "language": language,
                    "exit_code": result.returncode,
                    "stdout": result.stdout[:50000],
                    "stderr": result.stderr[:10000],
                },
                ensure_ascii=False,
                indent=2,
            )
        except subprocess.TimeoutExpired:
            return json.dumps(
                {
                    "language": language,
                    "exit_code": -1,
                    "stdout": "",
                    "stderr": f"Execution timeout after {timeout}s",
                    "error": "timeout",
                },
                ensure_ascii=False,
                indent=2,
            )
        except Exception as exc:
            return json.dumps(
                {
                    "language": language,
                    "exit_code": -1,
                    "stdout": "",
                    "stderr": str(exc),
                    "error": str(exc),
                },
                ensure_ascii=False,
                indent=2,
            )

    # =========================================================================
    # Answer Formatter Tool
    # =========================================================================

    @register_tool(
        name="answer_formatter",
        description="Format answer for competition scoring. Supports exact match, JSON canonical, list canonical, number precision, field extraction, and regex extraction.",
        input_schema=object_schema(
            {
                "raw_answer": {
                    "type": "string",
                    "description": "Raw answer text from LLM",
                },
                "format_type": {
                    "type": "string",
                    "description": "Format type: exact, json_canonical, list_canonical, number, field_extract, regex_extract",
                },
                "options": {
                    "type": "object",
                    "description": "Optional parameters (field for field_extract, pattern for regex_extract, precision for number)",
                    "default": {},
                },
            },
            ["raw_answer", "format_type"],
        ),
        kind="mcp",
        risk="low",
    )
    def answer_formatter(
        raw_answer: str,
        format_type: str,
        options: dict | None = None,
    ) -> str:
        """Format answer for competition scoring."""
        options = options or {}

        try:
            if format_type == "exact":
                return raw_answer.strip()

            elif format_type == "json_canonical":
                data = json.loads(raw_answer)
                def sort_obj(obj):
                    if isinstance(obj, dict):
                        return {k: sort_obj(v) for k, v in sorted(obj.items())}
                    elif isinstance(obj, list):
                        return [sort_obj(i) for i in obj]
                    return obj
                return json.dumps(sort_obj(data), ensure_ascii=False, indent=2)

            elif format_type == "list_canonical":
                items = json.loads(raw_answer)
                if isinstance(items, list):
                    unique = list(set(str(i) for i in items))
                    return json.dumps(sorted(unique), ensure_ascii=False)
                return raw_answer

            elif format_type == "number":
                precision = options.get("precision", 2)
                num = float(raw_answer)
                return str(round(num, precision))

            elif format_type == "field_extract":
                field = options.get("field")
                data = json.loads(raw_answer)
                return str(data.get(field, ""))

            elif format_type == "regex_extract":
                pattern = options.get("pattern")
                match = re.search(pattern, raw_answer)
                return match.group(1) if match else raw_answer

            else:
                return raw_answer

        except Exception:
            # 降级：解析失败返回原文
            return raw_answer

    # =========================================================================
    # P0 Competition Tools: date_compute, workday_calc, sql_query
    # =========================================================================

    @register_tool(
        name="date_compute",
        description="Parse a complete natural-language date sentence and compute its target date. Pass the full original sentence in expression so hours, calendar-week anchors, and fiscal-week starts are preserved.",
        input_schema=object_schema(
            {
                "expression": {
                    "type": "string",
                    "description": "Complete original sentence, e.g. '今天是2026年5月6日，明天是几号'. Do not shorten away hours or week anchors.",
                },
                "base_date": {
                    "type": "string",
                    "description": "Base date in YYYY-MM-DD format for relative date calculations",
                    "default": "",
                },
            },
            ["expression"],
        ),
        kind="mcp",
        risk="low",
    )
    def date_compute(expression: str, base_date: str = "") -> str:
        """Parse natural language date expressions and compute target dates."""
        try:
            from datetime import datetime, timedelta
            full_date_pattern = re.compile(
                r"(\d{4})\s*(?:年|[./-])\s*(\d{1,2})\s*(?:月|[./-])\s*(\d{1,2})"
            )

            def parse_datetime(year: int, month: int, day: int, start: int = 0) -> datetime:
                tail = expression[start:]
                hour_match = re.match(r"\s*(?:日)?\s*(\d{1,2})(?:点|时|[:.])", tail)
                hour = int(hour_match.group(1)) if hour_match else 0
                return datetime(year, month, day, hour)

            explicit_dates = list(full_date_pattern.finditer(expression))
            if base_date:
                try:
                    base = datetime.fromisoformat(base_date.strip())
                except ValueError:
                    base_match = full_date_pattern.search(base_date)
                    if not base_match:
                        raise
                    base = datetime(
                        int(base_match.group(1)),
                        int(base_match.group(2)),
                        int(base_match.group(3)),
                    )
            elif explicit_dates:
                match = explicit_dates[0]
                base = parse_datetime(
                    int(match.group(1)),
                    int(match.group(2)),
                    int(match.group(3)),
                    match.end(),
                )
            else:
                european = re.search(r"(?<!\d)(\d{1,2})/(\d{1,2})/(\d{4})(?!\d)", expression)
                month_day = re.search(r"(\d{1,2})月(\d{1,2})日?", expression)
                year = re.search(r"(20\d{2})年", expression)
                if european:
                    base = datetime(
                        int(european.group(3)),
                        int(european.group(2)),
                        int(european.group(1)),
                    )
                elif month_day and year:
                    base = datetime(
                        int(year.group(1)),
                        int(month_day.group(1)),
                        int(month_day.group(2)),
                    )
                else:
                    base = datetime.now()

            exp_lower = expression.lower()
            result = None
            weekday_numbers = {
                "一": 0,
                "二": 1,
                "三": 2,
                "四": 3,
                "五": 4,
                "六": 5,
                "日": 6,
                "天": 6,
            }

            # A statement such as "下周一是 2026-05-11" identifies the
            # current calendar week even though it does not state today's date.
            if not base_date:
                anchor = re.search(
                    r"下周([一二三四五六日天])是\s*"
                    + full_date_pattern.pattern,
                    expression,
                )
                if anchor:
                    known_weekday = weekday_numbers[anchor.group(1)]
                    known_date = datetime(
                        int(anchor.group(2)),
                        int(anchor.group(3)),
                        int(anchor.group(4)),
                    )
                    base = known_date - timedelta(days=7 + known_weekday)

            fiscal_week = re.search(
                r"财年第\s*(\d+)\s*周从\s*"
                + full_date_pattern.pattern
                + r".*?第\s*\1\s*周的周([一二三四五六日天])",
                expression,
            )
            calendar_week_matches = list(
                re.finditer(r"(上周|下周|本周|这周)(?:周)?([一二三四五六日天])", expression)
            )
            calendar_week = calendar_week_matches[-1] if calendar_week_matches else None
            named_weekday = re.search(r"第\s*\d+\s*周的周([一二三四五六日天])", expression)
            month_day_target = re.fullmatch(
                r"\s*(\d{1,2})月(\d{1,2})日?\s*",
                expression,
            )

            if fiscal_week:
                week_start = datetime(
                    int(fiscal_week.group(2)),
                    int(fiscal_week.group(3)),
                    int(fiscal_week.group(4)),
                )
                result = week_start + timedelta(
                    days=weekday_numbers[fiscal_week.group(5)] - week_start.weekday()
                )
            elif named_weekday:
                result = base + timedelta(
                    days=weekday_numbers[named_weekday.group(1)] - base.weekday()
                )
            elif "大后天" in expression:
                result = base + timedelta(days=3)
            elif "后天" in expression:
                result = base + timedelta(days=2)
            elif "明天" in expression or "明日" in expression:
                result = base + timedelta(days=1)
            elif "前天" in expression:
                result = base - timedelta(days=2)
            elif "昨天" in expression or "昨日" in expression:
                result = base - timedelta(days=1)
            elif calendar_week:
                week_offset = {"上周": -1, "本周": 0, "这周": 0, "下周": 1}[calendar_week.group(1)]
                week_start = base - timedelta(days=base.weekday())
                result = week_start + timedelta(
                    weeks=week_offset,
                    days=weekday_numbers[calendar_week.group(2)],
                )
            elif "last thursday" in exp_lower:
                result = base - timedelta(days=base.weekday() + 4)
            elif "last tuesday" in exp_lower:
                result = base - timedelta(days=base.weekday() + 6)
            elif "next tuesday" in exp_lower:
                result = base + timedelta(days=(7 - base.weekday()) + 1)
            elif "next thursday" in exp_lower:
                result = base + timedelta(days=(7 - base.weekday()) + 3)
            elif "去年今天" in expression or "去年今日" in expression or "last year" in exp_lower:
                try:
                    result = base.replace(year=base.year - 1)
                except ValueError:
                    result = base.replace(year=base.year - 1, day=28)
            elif "明年今天" in expression or "明年今日" in expression or "next year" in exp_lower:
                try:
                    result = base.replace(year=base.year + 1)
                except ValueError:
                    result = base.replace(year=base.year + 1, day=28)
            elif re.search(r"(\d+)\s*个?\s*小时", expression):
                hours = int(re.search(r"(\d+)\s*个?\s*小时", expression).group(1))
                result = base + timedelta(hours=hours)
            elif re.search(r"(\d+)\s*个?\s*自然日", expression):
                days = int(re.search(r"(\d+)\s*个?\s*自然日", expression).group(1))
                result = base + timedelta(days=days)
            elif re.search(r"(\d+)\s*天\s*(?:后|之后|以后)", expression):
                days = int(re.search(r"(\d+)\s*天\s*(?:后|之后|以后)", expression).group(1))
                result = base + timedelta(days=days)
            elif re.search(r"(\d+)\s*天\s*(?:前|之前|以前)", expression):
                days = int(re.search(r"(\d+)\s*天\s*(?:前|之前|以前)", expression).group(1))
                result = base - timedelta(days=days)
            elif "两周后" in expression:
                result = base + timedelta(weeks=2)
            elif re.search(r"(\d+)\s*(?:周|星期)\s*(?:后|之后|以后)", expression):
                weeks = int(
                    re.search(r"(\d+)\s*(?:周|星期)\s*(?:后|之后|以后)", expression).group(1)
                )
                result = base + timedelta(weeks=weeks)
            elif re.search(r"(\d+)\s*天", expression):
                result = base + timedelta(days=int(re.search(r"(\d+)\s*天", expression).group(1)))
            elif re.search(r"(\d+)\s*年后", expression):
                years = int(re.search(r"(\d+)\s*年后", expression).group(1))
                result = base.replace(year=base.year + years)
            elif "儿童节" in expression:
                result = base.replace(month=6, day=1, hour=0)
            elif "圣诞节" in expression:
                result = base.replace(month=12, day=25, hour=0)
            elif "元旦" in expression:
                result = base.replace(month=1, day=1, hour=0)
            elif month_day_target:
                result = base.replace(
                    month=int(month_day_target.group(1)),
                    day=int(month_day_target.group(2)),
                    hour=0,
                )
            elif explicit_dates:
                match = explicit_dates[-1]
                result = parse_datetime(
                    int(match.group(1)),
                    int(match.group(2)),
                    int(match.group(3)),
                    match.end(),
                )
                trailing_month_days = list(re.finditer(r"(\d{1,2})月(\d{1,2})日", expression))
                if trailing_month_days and trailing_month_days[-1].start() > match.end():
                    target = trailing_month_days[-1]
                    result = result.replace(
                        month=int(target.group(1)),
                        day=int(target.group(2)),
                        hour=0,
                    )
            else:
                european = re.search(r"(?<!\d)(\d{1,2})/(\d{1,2})/(\d{4})(?!\d)", expression)
                result = (
                    datetime(
                        int(european.group(3)),
                        int(european.group(2)),
                        int(european.group(1)),
                    )
                    if european
                    else base
                )

            if result:
                weekdays = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
                return json.dumps({
                    "expression": expression,
                    "base_date": base.strftime("%Y-%m-%d"),
                    "result": result.strftime("%Y-%m-%d"),
                    "weekday": weekdays[result.weekday()]
                }, ensure_ascii=False, indent=2)
            return json.dumps({"error": "Could not parse date expression"}, ensure_ascii=False)
        except Exception as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)

    @register_tool(
        name="workday_calc",
        description="Calculate dates considering working days (Mon-Fri). Supports 'X working days forward/backward'.",
        input_schema=object_schema(
            {
                "start_date": {
                    "type": "string",
                    "description": "Start date in YYYY-MM-DD format",
                },
                "days": {
                    "type": "integer",
                    "description": "Number of working days (positive=forward, negative=backward)",
                },
                "direction": {
                    "type": "string",
                    "description": "forward or backward",
                    "default": "forward",
                },
            },
            ["start_date", "days"],
        ),
        kind="mcp",
        risk="low",
    )
    def workday_calc(start_date: str, days: int, direction: str = "forward") -> str:
        """Calculate working days (Mon-Fri only)."""
        try:
            from datetime import datetime, timedelta

            start = datetime.strptime(start_date, "%Y-%m-%d")
            direction = direction.lower()
            if direction == "backward":
                days = -abs(days)
            else:
                days = abs(days)

            current = start
            count = 0
            step = 1 if days > 0 else -1

            while count < abs(days):
                current = current + timedelta(days=step)
                if current.weekday() < 5:
                    count += 1

            weekdays = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
            return json.dumps({
                "start_date": start_date,
                "working_days": abs(days),
                "result": current.strftime("%Y-%m-%d"),
                "weekday": weekdays[current.weekday()]
            }, ensure_ascii=False, indent=2)
        except Exception as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)

    @register_tool(
        name="sql_query",
        description="Execute SQL query on SQLite database and return results as JSON. Only SELECT queries allowed.",
        input_schema=object_schema(
            {
                "db_path": {
                    "type": "string",
                    "description": "Path to SQLite database file",
                },
                "query": {
                    "type": "string",
                    "description": "SQL query to execute (SELECT only for safety)",
                },
                "max_rows": {
                    "type": "integer",
                    "description": "Maximum rows to return",
                    "default": 100,
                },
            },
            ["db_path", "query"],
        ),
        kind="mcp",
        risk="medium",
    )
    def sql_query(db_path: str, query: str, max_rows: int = 100) -> str:
        """Execute SQL query on SQLite database."""
        try:
            import sqlite3
            path = Path(db_path)
            if not path.exists():
                return json.dumps({"error": f"Database not found: {db_path}"}, ensure_ascii=False)

            conn = sqlite3.connect(str(path))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            query_stripped = query.strip().upper()
            if not query_stripped.startswith("SELECT"):
                return json.dumps({"error": "Only SELECT queries are allowed"}, ensure_ascii=False)

            cursor.execute(query)
            rows = cursor.fetchmany(max_rows)
            columns = [desc[0] for desc in cursor.description] if cursor.description else []

            result_data = []
            for row in rows:
                result_data.append({col: row[i] for i, col in enumerate(columns)})

            conn.close()

            return json.dumps({
                "columns": columns,
                "rows": result_data,
                "count": len(result_data),
                "sql": query
            }, ensure_ascii=False, indent=2, default=str)
        except Exception as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)

    @register_tool(
        name="image_read",
        description="Read an image file and return base64 for multimodal analysis. Supports PNG, JPG, JPEG, BMP, GIF, WebP. The base64 data will be automatically included in the next LLM call as image content.",
        input_schema=object_schema(
            {
                "path": {
                    "type": "string",
                    "description": "Path to the image file",
                },
                "question": {
                    "type": "string",
                    "description": "Question about the image to ask the vision model (e.g., 'What text is shown?', 'Describe the error message').",
                    "default": "",
                },
            },
            ["path"],
        ),
        kind="mcp",
        risk="low",
    )
    def image_read(path: str, question: str = "") -> str:
        """Read image file and return base64 data for multimodal LLM call."""
        import base64

        img_path = Path(path)
        if not img_path.exists():
            return json.dumps({"error": f"Image file not found: {path}"}, ensure_ascii=False)

        suffix = img_path.suffix.lower()
        mime_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".bmp": "image/bmp",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        mime_type = mime_map.get(suffix, "image/png")
        if suffix not in mime_map:
            return json.dumps({"error": f"Unsupported image format: {suffix}"}, ensure_ascii=False)

        try:
            with open(img_path, "rb") as f:
                img_bytes = f.read()

            # Size check (max 10MB)
            if len(img_bytes) > 10 * 1024 * 1024:
                return json.dumps({"error": "Image too large (>10MB)"}, ensure_ascii=False)

            img_b64 = base64.b64encode(img_bytes).decode("utf-8")

            return json.dumps({
                "__image__": True,
                "path": str(img_path),
                "mime_type": mime_type,
                "base64": img_b64,
                "question": question or "请详细描述这张图片的内容，包括所有可见的文字、数字、表格、图表、错误信息等。",
            }, ensure_ascii=False)

        except Exception as exc:
            return json.dumps({"error": f"Image read failed: {exc}"}, ensure_ascii=False)
