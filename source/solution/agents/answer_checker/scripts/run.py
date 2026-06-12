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
            "你是答案验证和清理器。请完成两件事：\n\n"
            "【第一步：清理答案】\n"
            "从 answer_to_verify 中提取纯净答案：\n"
            "- 去掉所有 Thought:、Action:、Observation:、Final Answer: 及其内容\n"
            "- 去掉 <think>...</think> 标签\n"
            "- 去掉 VERIFIED 标记\n"
            "- 去掉解释性文字（如\"按规则...\"、\"经过分析...\"）\n"
            "- 只保留题目要求的答案正文\n\n"
            "【第二步：验证答案】\n"
            "检查清理后的答案是否满足 question_description 的要求：\n"
            "1. 格式是否正确（逗号分隔、JSON、列表等）\n"
            "2. 内容是否完整（不遗漏、不多余）\n"
            "3. 排序是否正确（如升序要求）\n"
            "4. 数值是否精确（无千分位、无单位）\n\n"
            "输出 JSON：\n"
            '{"overall_valid": true/false, "cleaned_answer": "清理后的纯净答案", "fix_suggestions": ["修改建议"], "summary": "一句话总结"}'
        ),
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
