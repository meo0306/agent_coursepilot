from pathlib import Path

import docx2txt

from coursepilot.rag.parsers.base import BaseParser
from coursepilot.rag.types import ParsedDocument, ParsedSection


class DOCXParser(BaseParser):
    supported_suffixes = {".docx"}

    def parse(self, path: str | Path) -> ParsedDocument:
        path = Path(path)
        content = docx2txt.process(str(path)).strip()
        sections = [ParsedSection(content=content)] if content else []
        return ParsedDocument(source_path=str(path), sections=sections)

