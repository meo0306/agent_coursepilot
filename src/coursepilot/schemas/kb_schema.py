from pydantic import BaseModel, Field


class KBSearchRequest(BaseModel):
    query: str = Field(min_length=1)
    chapter: str | None = None
    source_type: str | None = None
    verified_only: bool | None = None
    top_k: int = Field(default=5, ge=1, le=20)


class KBSearchResult(BaseModel):
    chunk_id: str
    course_id: str
    document_id: str | None = None
    source_type: str | None = None
    chapter: str | None = None
    section: str | None = None
    page: int | None = None
    title: str | None = None
    content: str
    score: float
    verified: bool = False


class KBSearchResponse(BaseModel):
    results: list[KBSearchResult]

