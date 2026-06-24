from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    course_id: str
    file_name: str
    file_path: str
    file_type: str
    source_type: str
    parse_status: str
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class DocumentBuildResponse(BaseModel):
    document_id: str
    course_id: str
    parse_status: str
    chunk_count: int
    error_message: str | None = None

