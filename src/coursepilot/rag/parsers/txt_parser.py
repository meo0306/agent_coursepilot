from pathlib import Path

from coursepilot.rag.parsers.base import BaseParser
from coursepilot.rag.types import ParsedDocument, ParsedSection


class TXTParser(BaseParser):
    supported_suffixes = {".txt"}

    def parse(self, path: str | Path) -> ParsedDocument:
        path = Path(path)
        try:
            content = path.read_text(encoding="utf-8").strip()
        except UnicodeDecodeError:
            content = path.read_text(encoding="gb18030").strip()
        sections = [ParsedSection(content=content)] if content else []
        return ParsedDocument(source_path=str(path), sections=sections)
