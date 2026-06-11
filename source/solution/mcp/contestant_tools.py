from __future__ import annotations

import csv
import io
import json
import re
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
        """Extract ZIP file and return detailed file list."""
        # Resolve relative paths from current working directory
        zip_path = Path(zip_path)
        if not zip_path.is_absolute():
            # Try relative to CWD first
            if not zip_path.exists():
                # Try relative to project root (parent of source/)
                project_root = Path.cwd()
                alt_path = project_root / zip_path
                if alt_path.exists():
                    zip_path = alt_path

        if not zip_path.exists():
            return json.dumps({"error": f"ZIP file not found: {zip_path}. CWD: {Path.cwd()}"}, ensure_ascii=False)

        if not output_dir:
            output_dir = tempfile.mkdtemp(prefix="zip_extract_")
        else:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)

        extracted = []
        inner_zips = []
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(output_dir)
                for name in zf.namelist():
                    file_path = Path(output_dir) / name
                    extracted.append(str(file_path))
                    # Detect inner ZIP files
                    if name.lower().endswith('.zip'):
                        inner_zips.append(str(file_path))
        except zipfile.BadZipFile:
            return json.dumps({"error": f"Invalid ZIP file: {zip_path}"}, ensure_ascii=False)
        except Exception as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)

        return json.dumps(
            {
                "output_dir": str(output_dir),
                "files": extracted,
                "count": len(extracted),
                "inner_zips": inner_zips,
                "has_inner_zip": len(inner_zips) > 0,
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
                tf.extractall(output_dir)
                extracted = [str(Path(output_dir) / name) for name in tf.getnames()]
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
        timeout: int = 30,
    ) -> str:
        """Execute code and return output."""
        language = language.lower()

        if language == "python":
            cmd = [sys.executable, "-c", code]
        elif language == "java":
            # Write to temp file, compile, run
            with tempfile.NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
                f.write(code)
                java_file = f.name
            class_file = java_file.replace(".java", ".class")
            try:
                # Compile
                compile_result = subprocess.run(
                    ["javac", java_file],
                    capture_output=True,
                    text=True,
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
                # Run
                class_name = Path(java_file).stem
                run_result = subprocess.run(
                    ["java", "-cp", str(Path(java_file).parent), class_name],
                    input=stdin,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
                return json.dumps(
                    {
                        "language": language,
                        "exit_code": run_result.returncode,
                        "stdout": run_result.stdout[:50000],
                        "stderr": run_result.stderr[:10000],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            finally:
                Path(java_file).unlink(missing_ok=True)
                Path(class_file).unlink(missing_ok=True)
        elif language == "node":
            cmd = ["node", "-e", code]
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
