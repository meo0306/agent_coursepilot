from abc import ABC, abstractmethod
from pathlib import Path

from coursepilot.rag.types import ParsedDocument


class BaseParser(ABC):
    # 每个 parser 声明自己支持哪些后缀
    supported_suffixes: set[str] = set()

    def supports(self, path: str | Path) -> bool:
        """用统一逻辑判断文件是否支持解析：后缀是否在白名单"""
        return Path(path).suffix.lower() in self.supported_suffixes

    @abstractmethod
    def parse(self, path: str | Path) -> ParsedDocument:
        """解析器抽象方法，具体实现见各详细parser，返回 ParsedDocument"""
        raise NotImplementedError


class UnsupportedParserError(ValueError):
    pass
