"""Plain text / markdown parser."""

from pathlib import Path
from .base import BaseParser, ParseResult, Section
from .pdf_parser import _is_heading, _make_section_ref, _make_parent_ref


class TextParser(BaseParser):
    def parse(self, file_path: Path) -> ParseResult:
        text = file_path.read_text(encoding="utf-8", errors="replace")
        sections: list[Section] = []
        section_index = 0
        current_title: str | None = None
        current_content: list[str] = []

        for line in text.split("\n"):
            stripped = line.strip()
            if not stripped:
                continue
            if _is_heading(stripped):
                if current_title and current_content:
                    ref = _make_section_ref(current_title, section_index)
                    sections.append(Section(
                        title=current_title,
                        content="\n".join(current_content),
                        section_ref=ref,
                        parent_ref=_make_parent_ref(ref),
                    ))
                    section_index += 1
                current_title = stripped
                current_content = []
            else:
                current_content.append(stripped)

        if current_title and current_content:
            ref = _make_section_ref(current_title, section_index)
            sections.append(Section(
                title=current_title,
                content="\n".join(current_content),
                section_ref=ref,
                parent_ref=_make_parent_ref(ref),
            ))

        if not sections:
            sections.append(Section(
                title="Document",
                content=text,
                section_ref="page-1",
            ))

        return ParseResult(
            filename=file_path.name,
            sections=sections,
            raw_text=text,
            page_count=1,
            metadata={"parser": "text"},
        )
