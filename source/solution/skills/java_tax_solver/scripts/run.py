from __future__ import annotations

import ast
import base64
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


def main() -> None:
    raw = sys.stdin.read().strip() or "{}"
    args = json.loads(raw)
    source_path = Path(str(args.get("source_path") or "")).resolve()
    question = args.get("question") or {}
    if not source_path.exists():
        raise SystemExit(f"source file not found: {source_path}")

    source = source_path.read_text(encoding="utf-8", errors="replace")
    deduction_point, brackets = extract_tax_parameters(source)
    hidden_cases = extract_hidden_cases(question)
    version_line = java_version_line()
    values = [
        f"{calculate_tax(float(salary), deduction_point, brackets):.2f}"
        for salary in hidden_cases
    ]
    print(",".join([version_line, *values]))


def java_version_line() -> str:
    try:
        completed = subprocess.run(
            ["java", "-version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            check=False,
        )
    except Exception as exc:
        return f'java version "unknown" ({type(exc).__name__}: {exc})'
    combined = "\n".join(
        line.strip()
        for line in [completed.stderr, completed.stdout]
        if line and line.strip()
    )
    first_line = next(
        (line.strip() for line in combined.splitlines() if "version" in line.lower()),
        "",
    )
    return first_line or 'java version "unknown"'


def extract_tax_parameters(source: str) -> tuple[float, list[list[float]]]:
    decoded_values = []
    for literal in re.findall(r'"([A-Za-z0-9+/=]{16,})"', source):
        decoded = triple_base64_decode(literal)
        if decoded:
            decoded_values.append(decoded)

    deduction_candidates: list[float] = []
    bracket_candidates: list[list[list[float]]] = []
    for value in decoded_values:
        stripped = value.strip()
        if re.fullmatch(r"\d+(?:\.\d+)?", stripped):
            deduction_candidates.append(float(stripped))
            continue
        if stripped.startswith("[[") and stripped.endswith("]]"):
            try:
                parsed = ast.literal_eval(stripped)
            except (SyntaxError, ValueError):
                continue
            if is_bracket_table(parsed):
                bracket_candidates.append(
                    [[float(cell) for cell in row] for row in parsed]
                )

    if not deduction_candidates:
        raise ValueError("could not decode deduction point from Java source")
    if not bracket_candidates:
        raise ValueError("could not decode tax bracket table from Java source")
    return deduction_candidates[0], bracket_candidates[0]


def triple_base64_decode(value: str) -> str | None:
    data: bytes = value.encode("ascii")
    try:
        for _ in range(3):
            data = base64.b64decode(data, validate=True)
        return data.decode("utf-8")
    except Exception:
        return None


def is_bracket_table(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(
            isinstance(row, list)
            and len(row) >= 4
            and all(isinstance(cell, (int, float)) for cell in row[:4])
            for row in value
        )
    )


def extract_hidden_cases(question: Any) -> list[int]:
    text = json.dumps(question, ensure_ascii=False) if not isinstance(question, str) else question
    marker = re.search(r"【隐藏用例】", text)
    if marker is None:
        marker = re.search(r"隐藏用例[：:]", text)
    if marker:
        text = text[marker.end():]
    format_marker = re.search(r"【返回格式】|返回格式", text)
    if format_marker:
        text = text[:format_marker.start()]

    numbers = [
        int(match.group(0))
        for match in re.finditer(r"(?<![\d.])\d{3,9}(?![\d.])", text)
    ]
    if not numbers:
        raise ValueError("could not parse hidden salary cases from question")
    return numbers


def calculate_tax(
    salary: float,
    deduction_point: float,
    brackets: list[list[float]],
) -> float:
    taxable_income = salary - deduction_point
    if taxable_income <= 0:
        return 0.0

    for row in brackets:
        lower, upper, rate, quick_deduction = row[:4]
        if lower <= taxable_income <= upper:
            return max(0.0, taxable_income * rate - quick_deduction)
    lower, upper, rate, quick_deduction = brackets[-1][:4]
    return max(0.0, taxable_income * rate - quick_deduction)


if __name__ == "__main__":
    main()
