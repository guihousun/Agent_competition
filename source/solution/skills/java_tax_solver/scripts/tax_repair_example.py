"""Reference pattern for Java personal income tax contest tasks.

This file is an example for the Agent to read and adapt. It is not a skill
entrypoint and should not be treated as a final-answer script. Keep the final
answer governed by the actual question wording and source file.
"""

from __future__ import annotations

import ast
import base64
import json
import re
import subprocess
from typing import Any


def java_version_line() -> str:
    completed = subprocess.run(
        ["java", "-version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=5,
        check=False,
    )
    combined = "\n".join(
        line.strip()
        for line in (completed.stderr, completed.stdout)
        if line and line.strip()
    )
    return next(
        (line for line in combined.splitlines() if "version" in line.lower()),
        'java version "unknown"',
    )


def triple_base64_decode(value: str) -> str | None:
    data = value.encode("ascii")
    try:
        for _ in range(3):
            data = base64.b64decode(data, validate=True)
        return data.decode("utf-8")
    except Exception:
        return None


def extract_tax_parameters(java_source: str) -> tuple[float, list[list[float]]]:
    deduction_candidates: list[float] = []
    bracket_candidates: list[list[list[float]]] = []
    for literal in re.findall(r'"([A-Za-z0-9+/=]{16,})"', java_source):
        decoded = triple_base64_decode(literal)
        if not decoded:
            continue
        value = decoded.strip()
        if re.fullmatch(r"\d+(?:\.\d+)?", value):
            deduction_candidates.append(float(value))
        elif value.startswith("[[") and value.endswith("]]"):
            parsed = ast.literal_eval(value)
            if is_bracket_table(parsed):
                bracket_candidates.append(
                    [[float(cell) for cell in row[:4]] for row in parsed]
                )
    if not deduction_candidates:
        raise ValueError("deduction point was not found in the Java source")
    if not bracket_candidates:
        raise ValueError("tax bracket table was not found in the Java source")
    return deduction_candidates[0], bracket_candidates[0]


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
    marker = re.search(r"【隐藏用例】", text) or re.search(r"隐藏用例[：:]", text)
    if marker:
        text = text[marker.end():]
    format_marker = re.search(r"【返回格式】|返回格式", text)
    if format_marker:
        text = text[:format_marker.start()]
    values = [
        int(match.group(0))
        for match in re.finditer(r"(?<![\d.])\d{3,9}(?![\d.])", text)
    ]
    if not values:
        raise ValueError("hidden salary cases were not found in the question")
    return values


def calculate_tax(salary: float, deduction_point: float, brackets: list[list[float]]) -> float:
    taxable_income = salary - deduction_point
    if taxable_income <= 0:
        return 0.0
    for lower, upper, rate, quick_deduction in brackets:
        if lower <= taxable_income <= upper:
            return max(0.0, taxable_income * rate - quick_deduction)
    lower, upper, rate, quick_deduction = brackets[-1]
    return max(0.0, taxable_income * rate - quick_deduction)


def build_answer(java_source: str, question: Any) -> str:
    deduction_point, brackets = extract_tax_parameters(java_source)
    values = [
        f"{calculate_tax(float(salary), deduction_point, brackets):.2f}"
        for salary in extract_hidden_cases(question)
    ]
    return ",".join([java_version_line(), *values])
