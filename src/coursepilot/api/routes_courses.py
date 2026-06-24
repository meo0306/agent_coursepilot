from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from coursepilot.db.session import get_session
from coursepilot.schemas.course_schema import CourseCreate, CourseRead, CourseUpdate
from coursepilot.services.course_service import CourseService

router = APIRouter(prefix="/courses", tags=["coursepilot-courses"])


@router.post("", response_model=CourseRead, status_code=status.HTTP_201_CREATED)
def create_course(payload: CourseCreate, session: Session = Depends(get_session)):
    return CourseService(session).create_course(payload)


@router.get("", response_model=list[CourseRead])
def list_courses(session: Session = Depends(get_session)):
    return CourseService(session).list_courses()


@router.get("/{course_id}", response_model=CourseRead)
def get_course(course_id: str, session: Session = Depends(get_session)):
    course = CourseService(session).get_course(course_id)
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    return course


@router.put("/{course_id}", response_model=CourseRead)
def update_course(
    course_id: str,
    payload: CourseUpdate,
    session: Session = Depends(get_session),
):
    course = CourseService(session).update_course(course_id, payload)
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    return course


@router.delete("/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_course(course_id: str, session: Session = Depends(get_session)):
    deleted = CourseService(session).delete_course(course_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)

