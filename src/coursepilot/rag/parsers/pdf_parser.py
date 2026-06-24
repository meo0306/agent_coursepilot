from pathlib import Path

import fitz

from coursepilot.rag.parsers.base import BaseParser
from coursepilot.rag.types import ParsedDocument, ParsedSection


class PDFParser(BaseParser):
    supported_suffixes = {".pdf"}

    def parse(self, path: str | Path) -> ParsedDocument:
        path = Path(path)
        sections: list[ParsedSection] = []
        with fitz.open(path) as doc:
            for index, page in enumerate(doc, start=1):
                content = page.get_text("text").strip()
                if content:
                    sections.append(ParsedSection(content=content, page=index))
        return ParsedDocument(source_path=str(path), sections=sections)

