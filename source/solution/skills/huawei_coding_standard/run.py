#!/usr/bin/env python3
"""华为编程规范 Skill - 规范查询."""

import json
import re
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent
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


def main():
    input_data = sys.stdin.read().strip()
    if not input_data:
        input_data = "{}"

    try:
        params = json.loads(input_data)
    except json.JSONDecodeError:
        params = {}

    language = params.get("language", "java")
    keyword = params.get("keyword", "")

    result = query_standards(language, keyword)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
