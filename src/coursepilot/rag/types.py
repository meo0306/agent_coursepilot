from dataclasses import dataclass, field


@dataclass(slots=True)
class ParsedSection:
    content: str
    page: int | None = None
    title: str | None = None
    metadata: dict[str, str | int | bool | None] = field(default_factory=dict)


@dataclass(slots=True)
class ParsedDocument:
    source_path: str
    sections: list[ParsedSection]
    metadata: dict[str, str | int | bool | None] = field(default_factory=dict)


@dataclass(slots=True)
class Chunk:
    id: str
    content: str
    course_id: str
    document_id: str
    source_type: str
    chapter: str | None = None
    section: str | None = None
    page: int | None = None
    title: str | None = None
    knowledge_points: list[str] = field(default_factory=list)
    verified: bool = False

