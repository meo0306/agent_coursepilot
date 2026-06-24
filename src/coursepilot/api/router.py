from fastapi import APIRouter

from coursepilot.api.routes_courses import router as courses_router
from coursepilot.api.routes_documents import router as documents_router
from coursepilot.api.routes_kb import router as kb_router
from coursepilot.api.routes_lessons import router as lessons_router

api_router = APIRouter(prefix="/api/coursepilot")
api_router.include_router(courses_router)
api_router.include_router(documents_router)
api_router.include_router(kb_router)
api_router.include_router(lessons_router)
