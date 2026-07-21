from pathlib import Path

from coursepilot.rag.parsers.base import BaseParser
from coursepilot.rag.types import ParsedDocument, ParsedSection


class MarkdownParser(BaseParser):
    supported_suffixes = {".md", ".markdown"}

    def parse(self, path: str | Path) -> ParsedDocument:
        path = Path(path)
        content = path.read_text(encoding="utf-8").strip()
        sections = [ParsedSection(content=content)] if content else []
        return ParsedDocument(source_path=str(path), sections=sections)
