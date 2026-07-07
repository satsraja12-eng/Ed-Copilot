from typing import TypedDict, List
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
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


BASE_DIR = os.path.dirname(os.path.dirname(__file__))
ADMIN_DB_DIR = os.path.join(BASE_DIR, "chroma_db_admin")

PERSONA_INSTRUCTIONS = {
    "student": "Explain simply. Use examples. Be encouraging.",
    "parent": "Give practical context. What should my child focus on?",
    "teacher": "Be precise. Reference the specific standard ID. Give full detail.",
}

# NC Math standard codes follow the Common Core domain convention, e.g.
# "NC.M1.A-CED.2" -> domain token "A-CED". Map each domain token to a
# plain-English name so students/parents can relate to a standard code
# immediately (e.g. "Creating Equations (NC.M1.A-CED.2)") instead of just
# seeing an opaque alphanumeric ID.
STANDARD_DOMAIN_NAMES = {
    "N-RN": "The Real Number System",
    "N-Q": "Quantities",
    "N-CN": "The Complex Number System",
    "A-SSE": "Seeing Structure in Expressions",
    "A-APR": "Arithmetic with Polynomials and Rational Expressions",
    "A-CED": "Creating Equations",
    "A-REI": "Reasoning with Equations and Inequalities",
    "F-IF": "Interpreting Functions",
    "F-BF": "Building Functions",
    "F-LE": "Linear, Quadratic, and Exponential Models",
    "F-TF": "Trigonometric Functions",
    "G-CO": "Congruence",
    "G-SRT": "Similarity, Right Triangles, and Trigonometry",
    "G-C": "Circles",
    "G-GPE": "Expressing Geometric Properties with Equations",
    "G-GMD": "Geometric Measurement and Dimension",
    "G-MG": "Modeling with Geometry",
    "S-ID": "Interpreting Categorical and Quantitative Data",
    "S-CP": "Conditional Probability and the Rules of Probability",
    "S-IC": "Making Inferences and Justifying Conclusions",
    "S-MD": "Using Probability to Make Decisions",
}


def describe_standard_id(standard_id: str) -> str:
    """Return a human-friendly label for a standard ID, e.g.
    'NC.M1.A-CED.2' -> 'Creating Equations (NC.M1.A-CED.2)'.
    Falls back to the raw ID if the domain token isn't recognized.
    """
    if not standard_id:
        return "Unknown Standard"
    parts = standard_id.split(".")
    domain_token = parts[2] if len(parts) >= 3 else None
    domain_name = STANDARD_DOMAIN_NAMES.get(domain_token)
    if domain_name:
        return f"{domain_name} ({standard_id})"
    return standard_id


ADMIN_PERSONA_INSTRUCTIONS = {
    "student": "Give a brief, direct answer. Keep it simple and friendly.",
    "parent": "Summarize the key points and list any action items for the family.",
    "teacher": "Provide the full policy text and include the source link.",
}

INTENT_BADGES = {
    "math_curriculum": "📐 Math Curriculum",
    "admin_policy": "🏫 District Policy",
    "college_guidance": "🎓 College Guidance",
    "out_of_scope": "🚫 Out of Scope",
}

# The math corpus (chroma_db/) only contains NC Math 1/2/3 standards. Districts
# outside NC (e.g. Frisco ISD, Plano ISD in Texas) must never receive NC
# curriculum content in response to a math question — that would be a
# cross-district/cross-state relevance leak, not a real answer for their state.
DISTRICT_STATE = {
    "wake_county_nc": "NC",
    "frisco_isd_tx": "TX",
    "plano_isd_tx": "TX",
}

DISTRICT_DISPLAY_NAME = {
    "wake_county_nc": "Wake County NC",
    "frisco_isd_tx": "Frisco ISD TX",
    "plano_isd_tx": "Plano ISD TX",
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


def _make_math_specialist(retriever):
    """Return a math_specialist node that uses the provided cached retriever."""

    def math_specialist(state: EdCopilotState) -> EdCopilotState:
        last_message = state["messages"][-1]["content"]
        persona = state.get("persona", "student").lower()
        persona_instruction = PERSONA_INSTRUCTIONS.get(
            persona, PERSONA_INSTRUCTIONS["student"]
        )

        district = state.get("district", "wake_county_nc")
        district_state = DISTRICT_STATE.get(district)
        if district_state != "NC":
            display_name = DISTRICT_DISPLAY_NAME.get(district, district)
            return {
                **state,
                "context_docs": [],
                "response": (
                    f"Our math curriculum content currently only covers North Carolina "
                    f"Math 1/2/3 standards, and does not apply to {display_name}. "
                    f"I don't want to give you NC-specific content that may not match "
                    f"{display_name}'s curriculum. Please check with your teacher or "
                    f"the district's academic office for TX curriculum standards."
                ),
            }

        docs = retriever.invoke(last_message)
        context = "\n\n".join(
            [
                f"[{describe_standard_id(doc.metadata.get('standard_id'))}] {doc.page_content}"
                for doc in docs
            ]
        )

        llm = _get_llm()
        math_prompt = ChatPromptTemplate.from_messages([
            ("system", (
                "You are a Math Curriculum Expert for NC schools.\n"
                "{persona_instruction}\n"
                "Answer using ONLY the provided educational standards context.\n"
                "If the context does not contain the answer, say "
                "'I cannot find this in our syllabus, please ask your teacher.'\n\n"
                "Whenever you reference a standard code (e.g. NC.M1.A-CED.2), NEVER cite "
                "the bare code alone. Always use the human-friendly domain name that is "
                "already given to you in brackets in the context below, formatted as "
                "'Domain Name (standard code)', e.g. 'Creating Equations (NC.M1.A-CED.2)'. "
                "This helps students immediately relate to what the standard covers.\n\n"
                "If the user asks how to plan, prepare, or study for the course, you MUST "
                "build a concrete week-by-week plan grounded ONLY in the specific topics "
                "found in the context above — never give generic advice like 'review the "
                "standards' or 'practice solving equations'. Group the actual standards/"
                "topics from the context into sequential weeks (e.g. 'Week 1: Creating "
                "Equations (NC.M1.A-CED.2) — justify solving methods and steps', "
                "'Week 2: Interpreting Functions (NC.M1.F-IF.1) — analyze tables and "
                "graphs to determine if a relation is a function'), using as many weeks "
                "as there are distinct topics in the context. Each week must name the "
                "real topic content, not a placeholder.\n\n"
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

    return math_specialist


def _get_admin_vectorstore():
    embeddings = HuggingFaceEmbeddings(model_name="BAAI/bge-small-en-v1.5")
    return Chroma(
        collection_name="admin_docs",
        persist_directory=ADMIN_DB_DIR,
        embedding_function=embeddings,
    )


def admin_specialist(state: EdCopilotState) -> EdCopilotState:
    query = state["messages"][-1]["content"]
    persona = state.get("persona", "parent").lower()
    district = state.get("district", "wake_county_nc")
    persona_instruction = ADMIN_PERSONA_INSTRUCTIONS.get(
        persona, ADMIN_PERSONA_INSTRUCTIONS["parent"]
    )

    if not os.path.exists(ADMIN_DB_DIR):
        return {
            **state,
            "context_docs": [],
            "response": (
                "Admin content has not been ingested yet. "
                "Please run `python src/admin_ingestion.py` to populate the knowledge base."
            ),
        }

    try:
        admin_vs = _get_admin_vectorstore()
        docs = admin_vs.similarity_search(
            query, k=5, filter={"district": district}
        )
        # Defence-in-depth: strip any chunk whose district tag does not match
        # the requested district in case the vectorstore returns unfiltered
        # results (e.g. a Chroma bug or a collection without metadata indexing).
        docs = [d for d in docs if d.metadata.get("district") == district]
    except Exception as e:
        return {
            **state,
            "context_docs": [],
            "response": f"Could not retrieve admin content: {e}",
        }

    if not docs:
        return {
            **state,
            "context_docs": [],
            "response": (
                "I don't have specific information about that for the selected district. "
                "Please check your district's official website for the most current details.\n\n"
                "_This information was scraped from public district websites. "
                "Verify at your district's official website._"
            ),
        }

    context_parts = []
    for doc in docs:
        label = doc.metadata.get("label", "document")
        source_url = doc.metadata.get("source_url", "")
        context_parts.append(f"[{label} | {source_url}]\n{doc.page_content}")
    context = "\n\n".join(context_parts)

    llm = _get_llm()
    admin_prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are a District Policy Expert for a school assistant.\n"
            "{persona_instruction}\n"
            "Answer using ONLY the provided district content below.\n"
            "If the context does not contain the answer, say "
            "'I don't have that specific information — please check the district's official website.'\n"
            "Always end your response with this disclaimer on its own line:\n"
            "_This information was scraped from public district websites. "
            "Verify at your district's official website._\n\n"
            "Context:\n{context}"
        )),
        ("human", "{question}"),
    ])

    chain = admin_prompt | llm | StrOutputParser()
    response = chain.invoke({
        "persona_instruction": persona_instruction,
        "context": context,
        "question": query,
    })

    # Guarantee the disclaimer is always present, even if the LLM omits it.
    _DISCLAIMER = (
        "_This information was scraped from public district websites. "
        "Verify at your district's official website._"
    )
    if _DISCLAIMER not in response:
        response = response.rstrip() + "\n\n" + _DISCLAIMER

    return {
        **state,
        "context_docs": docs,
        "response": response,
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


def build_graph(retriever):
    """Compile the Ed-Copilot StateGraph.

    Args:
        retriever: A pre-initialised WakeCountyRetriever (cached by the
                   caller via @st.cache_resource) so it is never rebuilt
                   per request.
    """
    graph = StateGraph(EdCopilotState)

    graph.add_node("classify_intent", classify_intent)
    graph.add_node("math_specialist", _make_math_specialist(retriever))
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
