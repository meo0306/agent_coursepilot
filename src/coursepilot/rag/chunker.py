import re
from uuid import uuid4

from coursepilot.rag.types import Chunk, ParsedDocument

HEADING_RE = re.compile(
    r"^\s*((第[一二三四五六七八九十百\d]+[章节篇])|(\d+(?:\.\d+){0,3})|"
    r"(chapter\s+\d+))[\s:：、.-]*(.*)$",
    re.IGNORECASE,
)


class Chunker:
    def __init__(self, chunk_size: int = 1000, overlap: int = 150):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def split(
        self,
        parsed: ParsedDocument,
        *,
        course_id: str,
        document_id: str,
        source_type: str,
    ) -> list[Chunk]:
        chunks: list[Chunk] = []
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
        chapter: str | None = None
        section_name: str | None = None
        title = initial_title
        buffer = ""
        chunks: list[Chunk] = []

        for paragraph in self._paragraphs(content):
            heading = HEADING_RE.match(paragraph)
            if heading:
                title = paragraph[:512]
                token = heading.group(1)
                if token.startswith("第") and ("章" in token or "篇" in token):
                    chapter = paragraph[:255]
                    section_name = None
                else:
                    section_name = paragraph[:255]

            if len(buffer) + len(paragraph) + 2 > self.chunk_size and buffer:
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
                buffer = buffer[-self.overlap :] if self.overlap > 0 else ""

            buffer = f"{buffer}\n\n{paragraph}".strip()

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
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n|\r\n\s*\r\n", content)]
        normalized: list[str] = []
        for paragraph in paragraphs:
            if not paragraph:
                continue
            if len(paragraph) <= self.chunk_size:
                normalized.append(paragraph)
                continue
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
        candidates = re.findall(r"[\u4e00-\u9fffA-Za-z][\u4e00-\u9fffA-Za-z0-9_-]{2,20}", content)
        seen: set[str] = set()
        keywords: list[str] = []
        for candidate in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            keywords.append(candidate)
            if len(keywords) >= 10:
                break
        return keywords

