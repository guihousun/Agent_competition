#!/usr/bin/env python3
"""Answer Checker Sub-agent - Pure prompt-driven verification."""

import json
import sys


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
    context_text = params.get("context_text", "")

    # 简单提取：如果 answer 为空，尝试从 task 中提取
    if not answer:
        task = params.get("task", "")
        # 不做复杂解析，直接把 task 当作待验证内容
        answer = task

    # 返回结构化输入，由 LLM prompt 驱动验证
    result = {
        "question_id": question.get("id", "unknown"),
        "question_description": question.get("description", ""),
        "answer_to_verify": answer,
        "context": context_text[:3000] if context_text else "",
        "instruction": (
            "请验证 answer_to_verify 是否满足 question_description 的要求。\n"
            "检查点：\n"
            "1. 格式是否正确（如逗号分隔、JSON、列表等）\n"
            "2. 内容是否完整（不遗漏、不多余）\n"
            "3. 排序是否正确（如升序要求）\n"
            "4. 是否包含解释文字（题目要求不要输出解释时）\n"
            "5. 数值是否精确（无千分位、无单位、精度正确）\n"
            "\n"
            "输出 JSON：\n"
            '{"overall_valid": true/false, "fix_suggestions": ["具体修改建议"], "summary": "一句话总结"}'
        ),
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
