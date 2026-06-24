from abc import ABC, abstractmethod
from pathlib import Path

from coursepilot.rag.types import ParsedDocument


class BaseParser(ABC):
    supported_suffixes: set[str] = set()

    def supports(self, path: str | Path) -> bool:
        return Path(path).suffix.lower() in self.supported_suffixes

    @abstractmethod
    def parse(self, path: str | Path) -> ParsedDocument:
        raise NotImplementedError


class UnsupportedParserError(ValueError):
    pass

