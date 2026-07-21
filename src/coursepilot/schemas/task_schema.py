from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class AsyncTaskAccepted(BaseModel):
    task_id: str
    status: Literal["pending"] = "pending"
    status_url: str


class AsyncTaskRead(BaseModel):
    task_id: str
    course_id: str
    task_type: str
    status: str
    result: Any | None = None
    error_message: str | None = None
    attempt_count: int
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
