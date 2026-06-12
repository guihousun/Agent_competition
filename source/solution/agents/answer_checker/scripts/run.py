#!/usr/bin/env python3
"""Answer Checker Sub-agent - Verifies answer format and correctness."""

import json
import sys
from datetime import datetime, timedelta


def check_format(answer: str, format_type: str) -> dict:
    """Check if answer matches required format."""
    errors = []

    if format_type == "exact":
        # 精确匹配：不应包含多余文字
        if len(answer) > 200:
            errors.append("Answer too long for exact match")
        if "答案是" in answer or "答案:" in answer:
            errors.append("Answer contains explanation text")

    elif format_type == "json":
        # JSON 字段匹配：检查字段顺序
        try:
            data = json.loads(answer)
            if isinstance(data, dict):
                keys = list(data.keys())
                if keys != sorted(keys):
                    errors.append(f"JSON keys not in alphabetical order: {keys} vs {sorted(keys)}")
        except json.JSONDecodeError:
            errors.append("Invalid JSON format")

    elif format_type == "list":
        # 列表匹配：检查排序和去重
        try:
            data = json.loads(answer)
            if isinstance(data, list):
                if data != sorted(data):
                    errors.append("List not sorted")
                if len(data) != len(set(data)):
                    errors.append("List contains duplicates")
        except json.JSONDecodeError:
            errors.append("Invalid JSON format")

    return {
        "format_type": format_type,
        "valid": len(errors) == 0,
        "errors": errors
    }


def check_date_calculation(expression: str, base_date_str: str, answer: str) -> dict:
    """Verify date calculation result."""
    try:
        base = datetime.strptime(base_date_str, "%Y-%m-%d")
        expected = None

        exp_lower = expression.lower()

        # 相对日期计算
        if "明天" in expression or "明日" in expression:
            expected = base + timedelta(days=1)
        elif "昨天" in expression or "昨日" in expression:
            expected = base - timedelta(days=1)
        elif "后天" in expression:
            expected = base + timedelta(days=2)
        elif "前天" in expression:
            expected = base - timedelta(days=2)
        elif "下周二" in expression:
            days_forward = (1 - base.weekday()) % 7
            if days_forward == 0:
                days_forward = 7
            expected = base + timedelta(days=days_forward)
        elif "下周三" in expression:
            days_forward = (2 - base.weekday()) % 7
            if days_forward == 0:
                days_forward = 7
            expected = base + timedelta(days=days_forward)
        elif "上周四" in expression:
            days_back = (base.weekday() - 3) % 7
            if days_back == 0:
                days_back = 7
            expected = base - timedelta(days=days_back)
        elif "去年今天" in expression or "去年今日" in expression:
            expected = base.replace(year=base.year - 1)
        elif "去年" in expression:
            expected = base.replace(year=base.year - 1)
        elif "下周" in expression:
            expected = base + timedelta(days=7)
        elif "上周" in expression:
            expected = base - timedelta(days=7)

        if expected:
            answer_date = datetime.strptime(answer, "%Y-%m-%d")
            if answer_date != expected:
                return {
                    "valid": False,
                    "expected": expected.strftime("%Y-%m-%d"),
                    "actual": answer,
                    "error": f"Date mismatch: expected {expected.strftime('%Y-%m-%d')}, got {answer}"
                }

        return {
            "valid": True,
            "expected": expected.strftime("%Y-%m-%d") if expected else "unknown",
            "actual": answer
        }

    except Exception as e:
        return {
            "valid": False,
            "error": str(e)
        }


def check_answer(question: dict, answer: str) -> dict:
    """Comprehensive answer check."""
    results = {
        "question_id": question.get("id", "unknown"),
        "checks": [],
        "overall_valid": True,
        "suggestions": []
    }

    # 1. 检查是否为空
    if not answer or not answer.strip():
        results["checks"].append({
            "type": "empty_check",
            "valid": False,
            "message": "Answer is empty"
        })
        results["overall_valid"] = False
        results["suggestions"].append("Answer should not be empty")
        return results

    # 2. 检查格式
    format_type = question.get("format_type", "exact")
    format_result = check_format(answer.strip(), format_type)
    results["checks"].append(format_result)
    if not format_result["valid"]:
        results["overall_valid"] = False
        results["suggestions"].extend(format_result["errors"])

    # 3. 检查日期计算（如果题目包含日期）
    question_text = question.get("description", "")
    if any(kw in question_text for kw in ["日期", "天", "周", "月", "年"]):
        # 提取 base_date
        base_date = question.get("base_date", "2026-05-06")
        date_result = check_date_calculation(question_text, base_date, answer.strip())
        results["checks"].append(date_result)
        if not date_result["valid"]:
            results["overall_valid"] = False
            results["suggestions"].append(date_result.get("error", ""))

    # 4. 检查长度合理性
    if len(answer) > 1000:
        results["checks"].append({
            "type": "length_check",
            "valid": False,
            "message": f"Answer too long ({len(answer)} chars)"
        })
        results["overall_valid"] = False
        results["suggestions"].append("Consider shortening the answer")

    # 5. 检查是否包含解释文字
    if "答案是" in answer or "答案:" in answer or "根据" in answer:
        results["checks"].append({
            "type": "explanation_check",
            "valid": False,
            "message": "Answer contains explanation text"
        })
        results["overall_valid"] = False
        results["suggestions"].append("Remove explanation text, output only the answer")

    return results


def main():
    """Main execution function."""
    input_data = sys.stdin.read().strip()
    if not input_data:
        input_data = '{}'

    try:
        params = json.loads(input_data)
    except json.JSONDecodeError:
        params = {}

    question = params.get("question", {})
    answer = params.get("answer", "")

    result = check_answer(question, answer)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
