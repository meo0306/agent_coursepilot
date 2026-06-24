from sqlalchemy import select
from sqlalchemy.orm import Session

from coursepilot.models import Course
from coursepilot.schemas.course_schema import CourseCreate, CourseUpdate


class CourseService:
    def __init__(self, session: Session):
        self.session = session

    def create_course(self, payload: CourseCreate) -> Course:
        course = Course(**payload.model_dump())
        self.session.add(course)
        self.session.commit()
        self.session.refresh(course)
        return course

    def list_courses(self) -> list[Course]:
        return list(self.session.scalars(select(Course).order_by(Course.created_at.desc())))

    def get_course(self, course_id: str) -> Course | None:
        return self.session.get(Course, course_id)

    def update_course(self, course_id: str, payload: CourseUpdate) -> Course | None:
        course = self.get_course(course_id)
        if course is None:
            return None

        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(course, key, value)
        self.session.commit()
        self.session.refresh(course)
        return course

    def delete_course(self, course_id: str) -> bool:
        course = self.get_course(course_id)
        if course is None:
            return False

        self.session.delete(course)
        self.session.commit()
        return True

