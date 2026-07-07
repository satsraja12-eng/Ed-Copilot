"""Master orchestrator — uses DistrictRegistry for plugin-based agent routing.

Flow:
  START -> classify_intent -> route_to_district -> agent_<district_id> -> END
                                                -> out_of_scope_handler  -> END

Adding a new district requires zero changes here. Just:
  1. Drop  config/tenants/<district>.yaml
  2. Drop  src/agents/<district>_agent.py  (implements DistrictAgent, exports `agent`)
  DistrictRegistry picks them up on startup and this graph auto-registers their nodes.
"""
from __future__ import annotations

from typing import List, TypedDict

from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
import os

from src.district_registry import DistrictRegistry


# ---------------------------------------------------------------------------
# Shared graph state
# ---------------------------------------------------------------------------

class EdCopilotState(TypedDict):
    messages: List[dict]
    persona: str
    district: str
    intent: str
    intent_badge: str
    context_docs: List[Document]
    response: str


# ---------------------------------------------------------------------------
# Intent badges (display only)
# ---------------------------------------------------------------------------

INTENT_BADGES = {
    "math_curriculum":  "📐 Math Curriculum",
    "course_catalog":   "📚 Course Catalog",
    "admin_policy":     "🏫 District Policy",
    "college_guidance": "🎓 College Guidance",
    "out_of_scope":     "🚫 Out of Scope",
}


# ---------------------------------------------------------------------------
# LLM factory
# ---------------------------------------------------------------------------

def _get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        base_url=os.environ.get("NEBIUS_BASE_URL", "https://api.studio.nebius.ai/v1/"),
        api_key=os.environ.get("NEBIUS_API_KEY", ""),
        model="meta-llama/Llama-3.3-70B-Instruct",
    )


# ---------------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------------

def classify_intent(state: EdCopilotState) -> EdCopilotState:
    """Classify the user's question into an intent category."""
    last_message = state["messages"][-1]["content"]
    district = state.get("district", "wake_county_nc")

    # Determine which intents are valid for this district.
    # TX districts use course_catalog; NC uses math_curriculum.
    is_tx = district.endswith("_tx")
    intent_options = (
        "- course_catalog: questions about course offerings, prerequisites, scheduling\n"
        "- admin_policy: questions about school calendars, policies, attendance, holidays\n"
        "- college_guidance: questions about course pathways, college admissions\n"
        "- out_of_scope: anything unrelated to school"
        if is_tx else
        "- math_curriculum: questions about NC Math 1, 2, or 3 content, standards, or concepts\n"
        "- admin_policy: questions about school calendars, policies, attendance, holidays\n"
        "- college_guidance: questions about course pathways, college admissions\n"
        "- out_of_scope: anything unrelated to school"
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are an intent classifier for a school assistant.\n"
            "Classify the user's question into exactly one of these categories:\n"
            f"{intent_options}\n\n"
            "Respond with ONLY the category label. No explanation."
        )),
        ("human", "{last_message}"),
    ])

    chain = prompt | _get_llm() | StrOutputParser()
    raw = chain.invoke({"last_message": last_message}).strip().lower()

    valid = {"math_curriculum", "course_catalog", "admin_policy", "college_guidance", "out_of_scope"}
    intent = raw if raw in valid else "out_of_scope"

    return {
        **state,
        "intent": intent,
        "intent_badge": INTENT_BADGES.get(intent, "❓ Unknown"),
    }


def out_of_scope_handler(state: EdCopilotState) -> EdCopilotState:
    return {
        **state,
        "context_docs": [],
        "response": (
            "I can help with school curriculum, district policies, and course planning. "
            "Could you rephrase your question in one of those areas?"
        ),
    }


# ---------------------------------------------------------------------------
# Graph builder — registry-driven, zero hardcoding per district
# ---------------------------------------------------------------------------

def build_graph(registry: DistrictRegistry):
    """Compile the master LangGraph.

    Args:
        registry: A DistrictRegistry loaded from config/tenants/*.yaml.
                  Each registered district agent becomes a graph node automatically.
    """
    graph = StateGraph(EdCopilotState)

    # -- Fixed nodes --
    graph.add_node("classify_intent", classify_intent)
    graph.add_node("out_of_scope_handler", out_of_scope_handler)

    # -- Plugin nodes: one per registered district agent --
    for district_id in registry.all_district_ids():
        agent = registry.get(district_id)
        node_name = f"agent_{district_id}"
        graph.add_node(node_name, agent.handle)

    # -- Routing: classify_intent -> district agent or out_of_scope --
    def route_after_classify(state: EdCopilotState) -> str:
        intent = state.get("intent", "out_of_scope")
        district = state.get("district", "")

        if intent == "out_of_scope":
            return "out_of_scope_handler"

        agent = registry.get(district)
        if agent and intent in agent.supported_intents:
            return f"agent_{district}"

        # District not registered or intent not supported → out of scope
        return "out_of_scope_handler"

    # Build the routing map for LangGraph
    routing_map: dict[str, str] = {"out_of_scope_handler": "out_of_scope_handler"}
    for district_id in registry.all_district_ids():
        routing_map[f"agent_{district_id}"] = f"agent_{district_id}"

    graph.set_entry_point("classify_intent")
    graph.add_conditional_edges("classify_intent", route_after_classify, routing_map)

    # All district agent nodes and out_of_scope lead to END
    graph.add_edge("out_of_scope_handler", END)
    for district_id in registry.all_district_ids():
        graph.add_edge(f"agent_{district_id}", END)

    return graph.compile()
