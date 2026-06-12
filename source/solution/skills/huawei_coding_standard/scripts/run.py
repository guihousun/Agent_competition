#!/usr/bin/env python3
"""华为编程规范 Skill - 查询规范与代码审查."""

import json
import os
import re
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
REFERENCES_DIR = SKILL_DIR / "references"


def load_references(language: str) -> dict[str, str]:
    """加载指定语言的规范文档."""
    refs = {}

    # 通用规范
    general_path = REFERENCES_DIR / "general.md"
    if general_path.exists():
        refs["general"] = general_path.read_text(encoding="utf-8")

    # 语言专属规范
    lang_map = {
        "c": "c_cpp.md", "cpp": "c_cpp.md", "c++": "c_cpp.md",
        "java": "java.md",
        "python": "python.md", "py": "python.md",
        "go": "go.md", "golang": "go.md",
        "js": "javascript.md", "javascript": "javascript.md",
        "ts": "typescript.md", "typescript": "typescript.md",
    }
    lang_file = lang_map.get(language.lower(), f"{language.lower()}.md")
    lang_path = REFERENCES_DIR / lang_file
    if lang_path.exists():
        refs[language] = lang_path.read_text(encoding="utf-8")

    return refs


def query_standards(language: str, keyword: str) -> dict:
    """查询规范中匹配关键词的内容."""
    refs = load_references(language)

    if not refs:
        return {
            "status": "no_references",
            "message": f"未找到 {language} 相关的规范文档，请将文档放入 references/ 目录",
            "available_files": [f.name for f in REFERENCES_DIR.glob("*.md")] if REFERENCES_DIR.exists() else [],
        }

    matches = []
    for lang, content in refs.items():
        sections = re.split(r"\n(?=#{1,4}\s)", content)
        for section in sections:
            if keyword.lower() in section.lower():
                matches.append({
                    "source": lang,
                    "content": section.strip()[:2000],
                })

    return {
        "status": "ok",
        "language": language,
        "keyword": keyword,
        "matches": matches[:10],
        "total_matches": len(matches),
    }


def review_code(language: str, code: str) -> dict:
    """审查代码是否符合华为规范."""
    refs = load_references(language)

    if not refs:
        return {
            "status": "no_references",
            "message": f"未找到 {language} 相关的规范文档，无法审查",
        }

    # 合并所有规范内容作为审查依据
    all_rules = "\n\n".join(refs.values())

    # 提取代码特征供 LLM 分析
    features = {
        "line_count": len(code.splitlines()),
        "has_comments": bool(re.search(r"//|/\*|#|'''", code)),
        "has_chinese_in_identifier": bool(re.search(r"[一-鿿]", code)),
    }

    # 常见问题快速检测
    issues = []

    # 命名规范检测
    if re.search(r"\b[a-z]+_[a-z]+\b", code) and language.lower() in ("java", "js", "ts"):
        issues.append("Java/JS 中变量名建议使用驼峰命名，不使用下划线")

    if re.search(r"\b[A-Z]{2,}[a-z]", code) and language.lower() in ("c", "cpp"):
        issues.append("C/C++ 中常量命名建议全大写下划线分隔")

    # 行长度检测
    long_lines = [i + 1 for i, line in enumerate(code.splitlines()) if len(line) > 120]
    if long_lines:
        issues.append(f"第 {long_lines[:5]} 行超过 120 字符")

    # 魔数检测
    magic_numbers = re.findall(r"(?<![a-zA-Z_])\b(?:1024|2048|65535|86400|3600)\b", code)
    if magic_numbers:
        issues.append(f"存在魔数 {set(magic_numbers)}，建议定义为常量")

    return {
        "status": "ok",
        "language": language,
        "features": features,
        "quick_issues": issues,
        "rules_for_llm": all_rules[:5000],
        "instruction": (
            "请根据华为编程规范审查以上代码。"
            "返回格式：\n"
            '{"issues": [{"line": N, "rule": "规范条款", "description": "问题描述", "fix": "修改建议"}], '
            '"summary": "总体评价"}'
        ),
    }


def main():
    input_data = sys.stdin.read().strip()
    if not input_data:
        input_data = "{}"

    try:
        params = json.loads(input_data)
    except json.JSONDecodeError:
        params = {}

    action = params.get("action", "query")
    language = params.get("language", "java")

    if action == "query":
        keyword = params.get("keyword", "")
        result = query_standards(language, keyword)
    elif action == "review":
        code = params.get("code", "")
        result = review_code(language, code)
    else:
        result = {"status": "error", "message": f"未知 action: {action}，支持 query / review"}

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
