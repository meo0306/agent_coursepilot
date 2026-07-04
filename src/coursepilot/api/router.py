"""
把业务接口拆成独立 router，方便后续拆分成独立服务

"""
from fastapi import APIRouter

from coursepilot.api.routes_courses import router as courses_router
from coursepilot.api.routes_documents import router as documents_router
from coursepilot.api.routes_exams import router as exams_router
from coursepilot.api.routes_files import router as files_router
from coursepilot.api.routes_kb import router as kb_router
from coursepilot.api.routes_lessons import router as lessons_router
from coursepilot.api.routes_ppt import router as ppt_router
from coursepilot.api.routes_reviews import router as reviews_router

# 统一注册子路由，
api_router = APIRouter(prefix="/api/coursepilot")

api_router.include_router(courses_router)
api_router.include_router(documents_router)
api_router.include_router(kb_router)
api_router.include_router(lessons_router)
api_router.include_router(exams_router)
api_router.include_router(ppt_router)
api_router.include_router(reviews_router)
api_router.include_router(files_router)
