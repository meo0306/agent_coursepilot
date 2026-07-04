"""
CoursePilot FastAPI route modules.
API 路由只负责 HTTP 层，如接收参数、抛异常等
"""

from coursepilot.api.router import api_router

__all__ = ["api_router"]
