"""
文本切分
把解析器输出的 ParsedDocument 切成多个适合 RAG 检索和向量化的 Chunk
段落切分 + 长段落滑窗 + chunk 间 overlap
"""

import re
from uuid import uuid4

from coursepilot.rag.knowledge_points import KnowledgePointExtractor
from coursepilot.rag.types import Chunk, ParsedDocument

# 标题识别正则
# 作用是在切块时识别当前段落是不是章节标题，然后给后续 chunk 填 chapter、section、title metadata
HEADING_RE = re.compile(
    r"^\s*((第[一二三四五六七八九十百\d]+[章节篇])|(\d+(?:\.\d+){0,3})|"
    r"(chapter\s+\d+))[\s:：、.-]*(.*)$",
    re.IGNORECASE,
)


class Chunker:
    def __init__(self, chunk_size: int = 1000, overlap: int = 150):
        self.chunk_size = chunk_size  # 目标 chunk 最大字符数
        self.overlap = overlap  # 相邻 chunk 之间保留 150 个字符重叠
        self.knowledge_point_extractor = KnowledgePointExtractor()

    def split(
        self,
        parsed: ParsedDocument,
        *,
        course_id: str,
        document_id: str,
        source_type: str,
    ) -> list[Chunk]:
        """
        chunker对外主入口
        接收解析后的文档和metadata
        输出切分后的chunks
        """
        chunks: list[Chunk] = []
        # 遍历ParsedDocument所有section，把 section.content 切成多个 Chunk，汇总所有 Chunk 返回
        for section in parsed.sections:
            chunks.extend(
                self._split_section(
                    section.content,
                    course_id=course_id,
                    document_id=document_id,
                    source_type=source_type,
                    page=section.page,
                    initial_title=section.title,
                )
            )
        return chunks

    def _split_section(
        self,
        content: str,
        *,
        course_id: str,
        document_id: str,
        source_type: str,
        page: int | None,
        initial_title: str | None,
    ) -> list[Chunk]:
        """核心切块函数，负责处理单个 section"""
        chapter: str | None = None
        section_name: str | None = None
        title = initial_title
        buffer = ""  # 正在累积的 chunk 内容
        chunks: list[Chunk] = []  # 已经生成的 chunk 列表
        # 把 section 拆成段落，然后逐段处理
        for paragraph in self._paragraphs(content):
            # 进行长度控制
            if len(buffer) + len(paragraph) + 2 > self.chunk_size and buffer:
                # 如果当前 buffer 再加上新段落会超过 chunk_size
                # 先把已有 buffer 做成一个 Chunk，
                chunks.append(
                    self._make_chunk(
                        buffer,
                        course_id=course_id,
                        document_id=document_id,
                        source_type=source_type,
                        chapter=chapter,
                        section=section_name,
                        page=page,
                        title=title,
                    )
                )
                # buffer 保留末尾 overlap 个字符
                buffer = buffer[-self.overlap :] if self.overlap > 0 else ""
            # 尝试识别标题
            heading = HEADING_RE.match(paragraph)
            if heading:
                title = paragraph[:512]
                token = heading.group(1)
                if token.startswith("第") and ("章" in token or "篇" in token):
                    chapter = paragraph[:255]
                    section_name = None
                else:
                    section_name = paragraph[:255]
            # 拼接新段落
            buffer = f"{buffer}\n\n{paragraph}".strip()
        # 循环结束后，如还有buffer，生成最后一个chunk
        if buffer:
            chunks.append(
                self._make_chunk(
                    buffer,
                    course_id=course_id,
                    document_id=document_id,
                    source_type=source_type,
                    chapter=chapter,
                    section=section_name,
                    page=page,
                    title=title,
                )
            )
        return chunks

    def _paragraphs(self, content: str) -> list[str]:
        """
        将内容按段落分割
        """
        # 按空行分段
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n|\r\n\s*\r\n", content)]
        normalized: list[str] = []
        for paragraph in paragraphs:
            # 过滤空段
            if not paragraph:
                continue
            # 如果长度不超过 chunk_size，直接保留
            if len(paragraph) <= self.chunk_size:
                normalized.append(paragraph)
                continue
            # 如果段落过长，按 chunk_size 切分，保留 overlap
            normalized.extend(
                paragraph[start : start + self.chunk_size]
                for start in range(0, len(paragraph), self.chunk_size - self.overlap)
            )
        return normalized

    def _make_chunk(
        self,
        content: str,
        *,
        course_id: str,
        document_id: str,
        source_type: str,
        chapter: str | None,
        section: str | None,
        page: int | None,
        title: str | None,
    ) -> Chunk:
        """统一创建 Chunk 对象"""
        return Chunk(
            id=str(uuid4()),
            content=content.strip(),
            course_id=course_id,
            document_id=document_id,
            source_type=source_type,
            chapter=chapter,
            section=section,
            page=page,
            title=title,
            knowledge_points=self._extract_keywords(content),
        )

    def _extract_keywords(self, content: str) -> list[str]:
        """
        从 chunk 内容里抽取最多 10 个候选关键词
        生产环境优先走 LLM 抽取，测试或未配置模型时使用 deterministic fallback
        """
        return self.knowledge_point_extractor.extract(content, max_points=10)
