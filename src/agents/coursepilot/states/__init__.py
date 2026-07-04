"""
CoursePilot graph state definitions.
LangGraph 节点之间传递的状态结构
每个节点只读写其中一部分字段
"""

from agents.coursepilot.states.exam_state import ExamGraphState
from agents.coursepilot.states.lesson_state import LessonGraphState
from agents.coursepilot.states.ppt_state import PPTGraphState

__all__ = ["ExamGraphState", "LessonGraphState", "PPTGraphState"]
