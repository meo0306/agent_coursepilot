"""
CoursePilot document parser modules.
该目录下定义多种类型文档解析器
"""

from pathlib import Path

from coursepilot.rag.parsers.base import BaseParser, UnsupportedParserError
from coursepilot.rag.parsers.docx_parser import DOCXParser
from coursepilot.rag.parsers.markdown_parser import MarkdownParser
from coursepilot.rag.parsers.pdf_parser import PDFParser
from coursepilot.rag.parsers.txt_parser import TXTParser
from coursepilot.rag.parsers.xlsx_parser import XLSXParser

PARSERS: tuple[BaseParser, ...] = (
    PDFParser(),
    DOCXParser(),
    MarkdownParser(),
    TXTParser(),
    XLSXParser(),
)


def get_parser(path: str | Path) -> BaseParser:
    """Parser 选择器: 根据文件路径获取对应的解析器实例"""
    suffix = Path(path).suffix.lower()
    for parser in PARSERS:
        if parser.supports(path):
            return parser
    raise UnsupportedParserError(f"Unsupported parser for file type: {suffix or '<none>'}")


__all__ = ["BaseParser", "UnsupportedParserError", "get_parser"]
