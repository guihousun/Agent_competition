#!/usr/bin/env python3
"""Build the prompt for the format-only answer checker."""

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
    if not answer:
        answer = params.get("task", "")

    question_parts = []
    for field in ("title", "question", "description", "explanation"):
        value = question.get(field)
        if isinstance(value, str) and value.strip() and value.strip() not in question_parts:
            question_parts.append(value.strip())
    question_description = "\n".join(question_parts)

    result = {
        "question_id": question.get("id", "unknown"),
        "question_description": question_description,
        "answer_to_verify": answer,
        "instruction": (
            "你是只负责最终答案格式的后检查器，不负责答案正确性。\n\n"
            "【严格边界】\n"
            "- 主 Agent 已独立完成解题；把 answer_to_verify 中的事实、数字、日期、ID 和列表成员视为既定内容。\n"
            "- 不得重新解题、重新计算、查询资料、读取文件或调用工具。\n"
            "- 不得改变事实、数字、日期、ID 或列表成员。\n"
            "- 不得因为你认为答案可能不正确而增加、删除、替换事实值或答案项。\n"
            "- 仅可处理格式问题：空答案、Markdown 代码块、<think> 标签、Final Answer 等包装、"
            "JSON 语法、引号/括号/转义、题目明确要求的分隔符和输出结构。\n"
            "- 只有题面明确要求排序时才可调整顺序；不得自行推断并改变内容。\n\n"
            "【处理步骤】\n"
            "1. 从 answer_to_verify 提取纯答案，去掉思考、解释、Markdown 围栏和结果对象包装。\n"
            "2. 对照 question_description，只检查最终输出格式。\n"
            "3. 格式合法时 overall_valid=true；cleaned_answer 和 corrected_answer 返回完整纯答案。\n"
            "4. 格式非法时 overall_valid=false；能仅靠格式操作修复则在 corrected_answer 返回完整修正版，"
            "否则 corrected_answer 返回空字符串。\n"
            "5. 空答案必须判为无效，不能编造内容补全。\n\n"
            "只输出 JSON 对象：\n"
            '{"overall_valid": true, "cleaned_answer": "纯答案", '
            '"corrected_answer": "仅格式修复后的完整答案或空字符串", '
            '"format_issues": ["格式问题"], "summary": "一句话总结"}'
        ),
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
