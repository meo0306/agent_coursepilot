"""
课程 CRUD（创建、读取、更新、删除）
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from coursepilot.models import Course
from coursepilot.schemas.course_schema import CourseCreate, CourseUpdate


class CourseService:
    def __init__(self, session: Session):
        self.session = session

    def create_course(self, payload: CourseCreate) -> Course:
        """创建课程"""
        course = Course(**payload.model_dump()) # Course(**...) 创建 ORM 对象，payload.model_dump()把 Pydantic 请求对象转成普通 dict
        self.session.add(course)    # 把对象加入数据库事务
        self.session.commit()   # 提交事务，真正写入数据库
        self.session.refresh(course)    # 重新读取数据库生成的字段
        return course   # 返回 ORM 对象给 FastAPI，FastAPI 再按 CourseRead schema 转成 JSON

    def list_courses(self) -> list[Course]:
        """列出所有课程，按创建时间倒序排列"""
        return list(self.session.scalars(select(Course).order_by(Course.created_at.desc())))

    def get_course(self, course_id: str) -> Course | None:
        """根据ID获取课程，返回课程对象或None"""
        return self.session.get(Course, course_id)

    def update_course(self, course_id: str, payload: CourseUpdate) -> Course | None:
        """更新课程"""
        course = self.get_course(course_id)
        if course is None:
            return None

        for key, value in payload.model_dump(exclude_unset=True).items():   # exclude_unset=True只更新用户真的传入的字段
            setattr(course, key, value)
        self.session.commit()
        self.session.refresh(course)
        return course

    def delete_course(self, course_id: str) -> bool:
        """删除课程"""
        course = self.get_course(course_id)
        if course is None:
            return False

        self.session.delete(course)
        self.session.commit()
        return True

