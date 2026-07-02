from typing import TypedDict, List
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
import os


class EdCopilotState(TypedDict):
    messages: List[dict]
    persona: str
    district: str
    intent: str
    context_docs: List[Document]
    response: str
    intent_badge: str


PERSONA_INSTRUCTIONS = {
    "student": "Explain simply. Use examples. Be encouraging.",
    "parent": "Give practical context. What should my child focus on?",
    "teacher": "Be precise. Reference the specific standard ID. Give full detail.",
}

INTENT_BADGES = {
    "math_curriculum": "📐 Math Curriculum",
    "admin_policy": "🏫 District Policy",
    "college_guidance": "🎓 College Guidance",
    "out_of_scope": "🚫 Out of Scope",
}


def _get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        base_url=os.environ.get("NEBIUS_BASE_URL", "https://api.studio.nebius.ai/v1/"),
        api_key=os.environ.get("NEBIUS_API_KEY", ""),
        model="meta-llama/Llama-3.3-70B-Instruct",
    )


def classify_intent(state: EdCopilotState) -> EdCopilotState:
    last_message = state["messages"][-1]["content"]
    llm = _get_llm()

    classify_prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are an intent classifier for a school assistant.\n"
            "Classify the user's question into exactly one of these four categories:\n"
            "- math_curriculum: questions about NC Math 1, 2, or 3 content, standards, or concepts\n"
            "- admin_policy: questions about school calendars, policies, board meetings, holidays, attendance\n"
            "- college_guidance: questions about course pathways, college admissions, high school planning\n"
            "- out_of_scope: anything unrelated to school\n\n"
            "Respond with ONLY the category label. No explanation."
        )),
        ("human", "{last_message}"),
    ])

    chain = classify_prompt | llm | StrOutputParser()
    raw = chain.invoke({"last_message": last_message}).strip().lower()

    valid = {"math_curriculum", "admin_policy", "college_guidance", "out_of_scope"}
    intent = raw if raw in valid else "out_of_scope"

    return {
        **state,
        "intent": intent,
        "intent_badge": INTENT_BADGES.get(intent, "❓ Unknown"),
    }


def math_specialist(state: EdCopilotState) -> EdCopilotState:
    from src.retrieval import get_hybrid_retriever

    last_message = state["messages"][-1]["content"]
    persona = state.get("persona", "student").lower()
    persona_instruction = PERSONA_INSTRUCTIONS.get(persona, PERSONA_INSTRUCTIONS["student"])

    retriever = get_hybrid_retriever()
    docs = retriever.invoke(last_message)

    context = "\n\n".join(
        [f"[{doc.metadata.get('standard_id')}] {doc.page_content}" for doc in docs]
    )

    llm = _get_llm()
    math_prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are a Math Curriculum Expert for NC schools.\n"
            "{persona_instruction}\n"
            "Answer using ONLY the provided educational standards context.\n"
            "If the context does not contain the answer, say "
            "'I cannot find this in our syllabus, please ask your teacher.'\n\n"
            "Context:\n{context}"
        )),
        ("human", "{question}"),
    ])

    chain = math_prompt | llm | StrOutputParser()
    response = chain.invoke({
        "persona_instruction": persona_instruction,
        "context": context,
        "question": last_message,
    })

    return {
        **state,
        "context_docs": docs,
        "response": response,
    }


def admin_specialist(state: EdCopilotState) -> EdCopilotState:
    return {
        **state,
        "context_docs": [],
        "response": (
            "Admin domain coming soon — it will answer policy and calendar questions."
        ),
    }


def guidance_stub(state: EdCopilotState) -> EdCopilotState:
    return {
        **state,
        "context_docs": [],
        "response": "College guidance planning is on the roadmap for Phase 2.",
    }


def out_of_scope_handler(state: EdCopilotState) -> EdCopilotState:
    return {
        **state,
        "context_docs": [],
        "response": (
            "I can help with NC school curriculum, district policies, and course planning. "
            "Could you rephrase your question in one of those areas?"
        ),
    }


def _route_intent(state: EdCopilotState) -> str:
    return state["intent"]


def build_graph() -> StateGraph:
    graph = StateGraph(EdCopilotState)

    graph.add_node("classify_intent", classify_intent)
    graph.add_node("math_specialist", math_specialist)
    graph.add_node("admin_specialist", admin_specialist)
    graph.add_node("guidance_stub", guidance_stub)
    graph.add_node("out_of_scope_handler", out_of_scope_handler)

    graph.set_entry_point("classify_intent")

    graph.add_conditional_edges(
        "classify_intent",
        _route_intent,
        {
            "math_curriculum": "math_specialist",
            "admin_policy": "admin_specialist",
            "college_guidance": "guidance_stub",
            "out_of_scope": "out_of_scope_handler",
        },
    )

    graph.add_edge("math_specialist", END)
    graph.add_edge("admin_specialist", END)
    graph.add_edge("guidance_stub", END)
    graph.add_edge("out_of_scope_handler", END)

    return graph.compile()
