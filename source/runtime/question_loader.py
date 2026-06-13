from __future__ import annotations

from pathlib import Path
from typing import Any

from source.runtime.question_schema import load_task_records, public_question_fields


def load_questions(path: str | Path) -> list[dict[str, Any]]:
    questions = []
    for item in load_task_records(path):
        public = public_question_fields(item)
        # Preserve title and description for runtime diagnostics.
        if "title" in item:
            public["title"] = item["title"]
        if "description" in item:
            public["description"] = item["description"]
        questions.append(public)
    return questions
