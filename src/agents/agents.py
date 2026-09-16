from dataclasses import dataclass

from langgraph.graph.state import CompiledStateGraph

from agents.coursepilot.graphs.exam_graph import coursepilot_exam_agent
from agents.coursepilot.graphs.lesson_graph import coursepilot_lesson_agent
from agents.coursepilot.graphs.ppt_graph import coursepilot_ppt_agent
from agents.coursepilot.states.exam_state import ExamGraphState
from agents.coursepilot.states.lesson_state import LessonGraphState
from agents.coursepilot.states.ppt_state import PPTGraphState
from schema import AgentInfo

DEFAULT_AGENT = "coursepilot-lesson-agent"

LessonAgentGraph = CompiledStateGraph[
    LessonGraphState,
    None,
    LessonGraphState,
    LessonGraphState,
]
ExamAgentGraph = CompiledStateGraph[
    ExamGraphState,
    None,
    ExamGraphState,
    ExamGraphState,
]
PPTAgentGraph = CompiledStateGraph[
    PPTGraphState,
    None,
    PPTGraphState,
    PPTGraphState,
]
AgentGraph = LessonAgentGraph | ExamAgentGraph | PPTAgentGraph
AgentGraphLike = AgentGraph


@dataclass
class Agent:
    description: str
    graph_like: AgentGraphLike


agents: dict[str, Agent] = {
    "coursepilot-lesson-agent": Agent(
        description="CoursePilot lesson planning agent prompt entrypoint.",
        graph_like=coursepilot_lesson_agent,
    ),
    "coursepilot-exam-agent": Agent(
        description="CoursePilot exam generation agent prompt entrypoint.",
        graph_like=coursepilot_exam_agent,
    ),
    "coursepilot-ppt-agent": Agent(
        description="CoursePilot PPT generation agent prompt entrypoint.",
        graph_like=coursepilot_ppt_agent,
    ),
}


async def load_agent(agent_id: str) -> None:
    """Validate that the requested CoursePilot agent is registered."""
    agents[agent_id]


def get_agent(agent_id: str) -> AgentGraph:
    """Get a registered CoursePilot agent graph."""
    return agents[agent_id].graph_like


def get_all_agent_info() -> list[AgentInfo]:
    return [
        AgentInfo(key=agent_id, description=agent.description) for agent_id, agent in agents.items()
    ]
