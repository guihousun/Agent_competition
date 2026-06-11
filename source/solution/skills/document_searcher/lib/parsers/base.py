"""Base parser interface with section_ref for FTS5 indexing."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional
from pathlib import Path


@dataclass
class Section:
    """Document section — equivalent to a legal provision."""
    title: str
    content: str
    section_ref: str
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    parent_ref: Optional[str] = None


@dataclass
class ParseResult:
    """Result of document parsing."""
    filename: str
    sections: List[Section]
    raw_text: str
    page_count: int
    metadata: dict


class BaseParser(ABC):
    """Base class for document parsers."""

    @abstractmethod
    def parse(self, file_path: Path) -> ParseResult:
        pass
