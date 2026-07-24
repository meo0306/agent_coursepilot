"""CourseRAG API schema layer.

P01 publishes HTTP paths and DTO contracts without mounting runtime routes.
"""

from courserag.api.http_schema import API_PREFIX

__all__ = ["API_PREFIX"]
