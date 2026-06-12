#!/usr/bin/env python3
"""Data Reader Sub-agent - Reads raw data and returns summaries or query chains."""

import json
import sys


def main():
    input_data = sys.stdin.read().strip()
    if not input_data:
        input_data = '{}'

    try:
        params = json.loads(input_data)
    except json.JSONDecodeError:
        params = {}

    question = params.get("question", "")
    files = params.get("files", [])
    context_text = params.get("context_text", "")

    # 返回结构化输入，由 LLM 读取数据并生成摘要
    result = {
        "task": question,
        "files_to_read": files,
        "context": context_text[:2000] if context_text else "",
        "instruction": (
            "请读取上述文件，根据任务需求返回以下两种格式之一：\n\n"
            "【格式 A：数据摘要】适用于需要了解数据全貌的场景\n"
            "{\n"
            '  "mode": "summary",\n'
            '  "data_overview": "数据结构、行列数、字段说明",\n'
            '  "key_findings": ["与任务相关的关键发现"],\n'
            '  "relevant_data": ["直接相关的数据片段（精简）"],\n'
            '  "suggested_queries": ["建议的精确查询步骤"]\n'
            "}\n\n"
            "【格式 B：精准查询链】适用于数据量大、需要精确定位的场景\n"
            "{\n"
            '  "mode": "query_chain",\n'
            '  "chain": [\n'
            "    {\n"
            '      "step": 1,\n'
            '      "action": "具体操作（如：读取 CSV 第 X-Y 行）",\n'
            '      "tool": "使用的工具",\n'
            '      "params": {"key": "value"},\n'
            '      "purpose": "这步的目的"\n'
            "    }\n"
            "  ],\n"
            '  "expected_result": "最终期望获得的数据"\n'
            "}\n\n"
            "选择依据：\n"
            "- 数据量小（<100行）或需要全貌理解 → 格式 A\n"
            "- 数据量大（>100行）或需要精确筛选 → 格式 B\n"
            "- 邮件/日志等非结构化文本 → 格式 A，提取关键段落\n"
            "- CSV/DB 等结构化数据 → 格式 B，给出精确查询\n\n"
            "要求：\n"
            "- 不要返回原始数据全文，只返回摘要或查询链\n"
            "- relevant_data 中的数据片段控制在 500 字以内\n"
            "- 输出纯 JSON，不要解释"
        ),
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
