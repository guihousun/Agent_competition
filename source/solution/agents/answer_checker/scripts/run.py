#!/usr/bin/env python3
"""Answer Checker Sub-agent - Verifies answer against question requirements and provides fix suggestions."""

import json
import sys
import re
from datetime import datetime, timedelta


def check_format(answer: str, format_type: str) -> dict:
    """Check if answer matches required format."""
    errors = []
    suggestions = []

    if format_type == "exact":
        # 精确匹配：不应包含多余文字
        if len(answer) > 200:
            errors.append("Answer too long for exact match")
            suggestions.append(f"Answer is {len(answer)} chars, should be under 200")
        if "答案是" in answer or "答案:" in answer or "根据" in answer:
            errors.append("Answer contains explanation text")
            suggestions.append("Remove explanation text like '答案是', '答案:', '根据'")

    elif format_type == "json":
        # JSON 字段匹配：检查字段顺序
        try:
            data = json.loads(answer)
            if isinstance(data, dict):
                keys = list(data.keys())
                if keys != sorted(keys):
                    errors.append(f"JSON keys not in alphabetical order: {keys} vs {sorted(keys)}")
                    suggestions.append(f"Reorder JSON keys alphabetically: {sorted(keys)}")
        except json.JSONDecodeError:
            errors.append("Invalid JSON format")
            suggestions.append("Fix JSON syntax errors")

    elif format_type == "list":
        # 列表匹配：检查排序和去重
        try:
            data = json.loads(answer)
            if isinstance(data, list):
                if data != sorted(data):
                    errors.append("List not sorted")
                    suggestions.append(f"Sort the list: {sorted(data)}")
                if len(data) != len(set(data)):
                    errors.append("List contains duplicates")
                    suggestions.append(f"Remove duplicates: {list(set(data))}")
        except json.JSONDecodeError:
            errors.append("Invalid JSON format")
            suggestions.append("Fix JSON syntax errors")

    return {
        "format_type": format_type,
        "valid": len(errors) == 0,
        "errors": errors,
        "suggestions": suggestions
    }


def check_date_calculation(expression: str, base_date_str: str, answer: str) -> dict:
    """Verify date calculation result and provide fix suggestion."""
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
                    "error": f"Date mismatch: expected {expected.strftime('%Y-%m-%d')}, got {answer}",
                    "suggestion": f"Change '{answer}' to '{expected.strftime('%Y-%m-%d')}'"
                }

        return {
            "valid": True,
            "expected": expected.strftime("%Y-%m-%d") if expected else "unknown",
            "actual": answer,
            "suggestion": None
        }

    except Exception as e:
        return {
            "valid": False,
            "error": str(e),
            "suggestion": "Check date format and calculation logic"
        }


def parse_question_requirements(description: str) -> dict:
    """Parse question description to extract requirements."""
    requirements = {
        "format": "exact",  # default
        "has_date_calculation": False,
        "has_json_output": False,
        "has_list_output": False,
        "expected_count": None,
        "base_date": None
    }

    desc_lower = description.lower()

    # 检测日期计算
    if any(kw in desc_lower for kw in ["日期", "天", "周", "月", "年", "星期"]):
        requirements["has_date_calculation"] = True
        # 提取 base_date
        date_match = re.search(r'(\d{4})[年\-/](\d{1,2})[月\-/](\d{1,2})', description)
        if date_match:
            requirements["base_date"] = f"{date_match.group(1)}-{date_match.group(2).zfill(2)}-{date_match.group(3).zfill(2)}"

    # 检测 JSON 输出
    if "json" in desc_lower or "输出格式" in description:
        requirements["has_json_output"] = True
        requirements["format"] = "json"

    # 检测列表输出
    if "逗号分隔" in description or "，分隔" in description or "列表" in desc_lower:
        requirements["has_list_output"] = True
        requirements["format"] = "list"

    # 检测期望数量
    count_match = re.search(r'(\d+)\s*个', description)
    if count_match:
        requirements["expected_count"] = int(count_match.group(1))

    return requirements


def check_answer_against_requirements(question: dict, answer: str) -> dict:
    """Check answer against question requirements and provide fix suggestions."""
    description = question.get("description", "")
    task = question.get("task", "")
    full_text = description + " " + task

    # 解析题目要求（使用完整文本）
    requirements = parse_question_requirements(full_text)

    results = {
        "question_id": question.get("id", "unknown"),
        "requirements": requirements,
        "checks": [],
        "overall_valid": True,
        "fix_suggestions": []
    }

    # 1. 检查答案是否为空
    if not answer or not answer.strip():
        results["checks"].append({
            "type": "empty_check",
            "valid": False,
            "message": "Answer is empty"
        })
        results["overall_valid"] = False
        results["fix_suggestions"].append("Provide an answer, not empty string")
        return results

    answer = answer.strip()

    # 2. 检查格式
    format_result = check_format(answer, requirements["format"])
    results["checks"].append(format_result)
    if not format_result["valid"]:
        results["overall_valid"] = False
        results["fix_suggestions"].extend(format_result["suggestions"])

    # 3. 检查日期计算
    if requirements["has_date_calculation"]:
        base_date = requirements.get("base_date", "2026-05-06")
        date_expressions = re.findall(r'(上周[一二三四五六日天]|下周[一二三四五六日天]|昨天|明天|后天|前天|去年今天|去年今日)', full_text)
        answer_dates = re.findall(r'\d{4}-\d{2}-\d{2}', answer)

        if date_expressions and answer_dates:
            for expr, ans_date in zip(date_expressions, answer_dates):
                date_result = check_date_calculation(expr, base_date, ans_date)
                results["checks"].append(date_result)
                if not date_result["valid"]:
                    results["overall_valid"] = False
                    if date_result.get("suggestion"):
                        results["fix_suggestions"].append(date_result["suggestion"])
        elif date_expressions and not answer_dates:
            results["checks"].append({
                "type": "date_check",
                "valid": False,
                "message": "Date calculation required but no date found in answer"
            })
            results["overall_valid"] = False
            results["fix_suggestions"].append("Add calculated date in YYYY-MM-DD format")

    # 4. 检查答案数量（如果题目指定期望数量）
    if requirements["expected_count"]:
        # 统计答案中的项目数（逗号分隔或 JSON 数组）
        if requirements["format"] == "list":
            try:
                data = json.loads(answer)
                if isinstance(data, list) and len(data) != requirements["expected_count"]:
                    results["checks"].append({
                        "type": "count_check",
                        "valid": False,
                        "message": f"Expected {requirements['expected_count']} items, got {len(data)}"
                    })
                    results["overall_valid"] = False
                    results["fix_suggestions"].append(f"Answer should contain exactly {requirements['expected_count']} items")
            except:
                pass
        else:
            # 逗号分隔的字符串
            items = [x.strip() for x in answer.split(",") if x.strip()]
            if len(items) != requirements["expected_count"]:
                results["checks"].append({
                    "type": "count_check",
                    "valid": False,
                    "message": f"Expected {requirements['expected_count']} items, got {len(items)}"
                })
                results["overall_valid"] = False
                results["fix_suggestions"].append(f"Answer should contain exactly {requirements['expected_count']} items, separated by commas")

    # 5. 检查是否包含解释文字
    if "答案是" in answer or "答案:" in answer or "根据" in answer:
        results["checks"].append({
            "type": "explanation_check",
            "valid": False,
            "message": "Answer contains explanation text"
        })
        results["overall_valid"] = False
        results["fix_suggestions"].append("Remove explanation text, output ONLY the answer (no '答案是', '根据', etc.)")

    # 6. 生成最终建议摘要
    if not results["overall_valid"]:
        results["summary"] = f"Answer needs fixes: {'; '.join(results['fix_suggestions'])}"
    else:
        results["summary"] = "Answer looks good!"

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

    result = check_answer_against_requirements(question, answer)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
