#!/usr/bin/env python3
"""Data Reader Sub-agent - Data interface layer for the main agent.

Two-phase design:
  Phase 1: Return data OVERVIEW (schema, counts, field values, structure) — no filtering
  Phase 2: Execute precise queries as instructed by main agent

The data_reader NEVER does "initial screening" based on the question.
It always returns the full landscape so the main agent can decide what's relevant.
"""

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
    mode = params.get("mode", "overview")  # "overview" or "query"

    if mode == "overview":
        # Phase 1: 返回数据全貌，不做任何筛选
        result = {
            "mode": "overview",
            "files": files,
            "instruction": (
                "请读取上述文件，返回数据全貌。不要做任何筛选或过滤。\n\n"
                "输出 JSON：\n"
                "{\n"
                '  "files_read": ["已读取的文件路径"],\n'
                '  "data_landscape": {\n'
                '    "filename": {\n'
                '      "type": "csv/json/db/txt/log/email",\n'
                '      "structure": "行数、列数、数据类型",\n'
                '      "fields": [{"name": "字段名", "type": "类型", "sample": "示例值", "unique_count": 10}],\n'
                '      "value_ranges": {"数值字段": {"min": 0, "max": 100}, "分类字段": ["值1", "值2"]},\n'
                '      "notable": ["值得注意的数据特征，如空值、异常值、特殊编码"]\n'
                "    }\n"
                "  },\n"
                '  "connections": ["文件之间的关联关系，如外键、引用"],\n'
                '  "potential_issues": ["可能影响后续分析的问题，如缺失值、重复行"]\n'
                "}\n\n"
                "要求：\n"
                "- 不要省略任何字段或文件\n"
                "- 不要基于题目做筛选，题目仅供参考\n"
                "- value_ranges 列出所有枚举值（如果<20个）或 min/max\n"
                "- 输出纯 JSON，不要解释"
            ),
        }
    else:
        # Phase 2: 按主 agent 指令执行精确查询
        result = {
            "mode": "query",
            "query": question,
            "files": files,
            "context": context_text[:2000] if context_text else "",
            "instruction": (
                "请根据上述查询指令，执行精确的数据查询。\n\n"
                "输出 JSON：\n"
                "{\n"
                '  "query_executed": "实际执行的查询描述",\n'
                '  "result_count": 10,\n'
                '  "results": [查询结果数组，控制在 50 条以内],\n'
                '  "result_summary": "结果的简要说明",\n'
                '  "caveats": ["需要注意的限制或假设"]\n'
                "}\n\n"
                "要求：\n"
                "- 严格按照查询指令执行，不要擅自扩大或缩小范围\n"
                "- 如果查询条件不明确，返回所有可能的结果并说明\n"
                "- results 控制在 50 条以内，超过时说明总数并返回前 50 条\n"
                "- 输出纯 JSON，不要解释"
            ),
        }

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
