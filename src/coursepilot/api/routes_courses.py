from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from coursepilot.db.session import get_session
from coursepilot.schemas.course_schema import CourseCreate, CourseRead, CourseUpdate
from coursepilot.services.course_service import CourseService

# 路由都会以/api/coursepilot/courses
router = APIRouter(prefix="/courses", tags=["coursepilot-courses"])


@router.post("", response_model=CourseRead, status_code=status.HTTP_201_CREATED)    # 路由装饰器（_、响应模型、状态码）
def create_course(payload: CourseCreate, session: Session = Depends(get_session)):  # 创建课程接口（请求体模型，依赖注入）
    return CourseService(session).create_course(payload)    # 调用服务层创建课程，并返回创建的课程数据


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

