from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from coursepilot.db.session import get_session
from coursepilot.models import ExportFile
from coursepilot.schemas.lesson_schema import ExportFileRead

router = APIRouter(tags=["coursepilot-files"])


@router.get("/files/{file_id}", response_model=ExportFileRead)
def get_file(file_id: str, session: Session = Depends(get_session)):
    file = session.get(ExportFile, file_id)
    if file is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return file


@router.get("/files/{file_id}/download")
def download_file(file_id: str, session: Session = Depends(get_session)):
    file = session.get(ExportFile, file_id)
    if file is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    path = Path(file.file_path)
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File missing on disk")
    return FileResponse(path=path, filename=file.file_name)
