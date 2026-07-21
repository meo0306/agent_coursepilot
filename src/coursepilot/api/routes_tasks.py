from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from coursepilot.db.session import get_session
from coursepilot.schemas.task_schema import AsyncTaskRead
from coursepilot.services.async_task_service import AsyncTaskService

router = APIRouter(tags=["coursepilot-tasks"])


@router.get("/tasks/{task_id}", response_model=AsyncTaskRead)
def get_async_task(task_id: str, session: Session = Depends(get_session)):
    task = AsyncTaskService(session).get(task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task
