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
        "question_description": question.get("question", question.get("description", "")),
        "answer_to_verify": answer,
        "context": context_text[:65536] if context_text else "",
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
            "4. 数值是否精确（无千分位、无单位）\n"
            "5. 日期、数字和结构化结果必须使用可用工具重新计算，不能直接相信候选答案或旧工具结果\n"
            "6. 复算日期时必须把原始完整消息作为 expression，保留小时、自然周和财年周等上下文\n\n"
            "在输出最终 JSON 前必须至少调用一次工具。对于逐行日期任务，必须对每一条原始消息分别调用 date_compute；"
            "工作日问题调用 workday_calc。不得自行心算替代工具结果。\n\n"
            "输出 JSON：\n"
            '{"overall_valid": true/false, "cleaned_answer": "只做去标签和去解释后的候选答案", '
            '"corrected_answer": "基于工具复算后的完整修正版；若原答案正确则与cleaned_answer相同；无法可靠修正则为空字符串", '
            '"fix_suggestions": ["修改建议"], "summary": "一句话总结"}\n'
            "corrected_answer 必须保持题目要求的最终输出格式，并包含完整答案，不能只返回局部修改片段。"
        ),
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
