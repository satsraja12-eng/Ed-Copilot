import streamlit as st
from src.orchestrator import build_graph, EdCopilotState
from src.retrieval import get_hybrid_retriever
import os
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="Ed-Copilot", page_icon="🎓", layout="centered")

st.title("🎓 Ed-Copilot")
st.caption("Your AI school assistant for NC Math, district policy, and course planning.")

st.warning(
    "⚠️ Created for learning purposes. Please refer to your county's official website "
    "for authoritative information.",
    icon="📋",
)

@st.cache_resource(show_spinner="Loading retrieval pipeline...")
def init_retriever():
    return get_hybrid_retriever()


@st.cache_resource(show_spinner="Initializing Ed-Copilot...")
def init_graph(_retriever):
    api_key = os.environ.get("NEBIUS_API_KEY", "")
    if not api_key or api_key == "your-key-here":
        st.error("Please add your NEBIUS_API_KEY to the .env file.")
        st.stop()
    return build_graph(_retriever)


retriever = init_retriever()
graph = init_graph(retriever)

with st.sidebar:
    st.header("⚙️ Settings")

    persona = st.selectbox(
        "Who are you?",
        options=["student", "parent", "teacher"],
        format_func=lambda x: {"student": "🧑‍🎓 Student", "parent": "👨‍👩‍👧 Parent", "teacher": "👩‍🏫 Teacher"}[x],
        key="persona",
    )

    district = st.selectbox(
        "District",
        options=["wake_county_nc", "frisco_isd_tx", "plano_isd_tx"],
        format_func=lambda x: {
            "wake_county_nc": "Wake County NC",
            "frisco_isd_tx": "Frisco ISD TX",
            "plano_isd_tx": "Plano ISD TX",
        }[x],
        key="district",
    )

    st.divider()
    if st.button("🗑️ Clear chat"):
        st.session_state.messages = []
        st.rerun()

if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        if message["role"] == "assistant" and message.get("badge"):
            st.caption(message["badge"])
        st.markdown(message["content"])
        if message.get("sources"):
            with st.expander("View Retrieved Sources"):
                for src in message["sources"]:
                    st.write(f"**{src['standard_id']}** (Course: {src['course_id']}) — Rerank Score: {src['rerank_score']:.2f}")
                    st.caption(src["snippet"])

if prompt := st.chat_input("Ask about NC Math, school policy, or course planning..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                state = EdCopilotState(
                    messages=st.session_state.messages,
                    persona=st.session_state.get("persona", "student"),
                    district=st.session_state.get("district", "wake_county_nc"),
                    intent="",
                    context_docs=[],
                    response="",
                    intent_badge="",
                )
                result = graph.invoke(state)
                response = result["response"]
                badge = result["intent_badge"]
                docs = result.get("context_docs", [])

                st.caption(badge)
                st.markdown(response)

                sources = []
                if docs:
                    with st.expander("View Retrieved Sources"):
                        for doc in docs:
                            sid = doc.metadata.get("standard_id", "—")
                            cid = doc.metadata.get("course_id", "—")
                            score = doc.metadata.get("rerank_score", 0.0)
                            snippet = doc.page_content[:300] + "..."
                            st.write(f"**{sid}** (Course: {cid}) — Rerank Score: {score:.2f}")
                            st.caption(snippet)
                            sources.append({
                                "standard_id": sid,
                                "course_id": cid,
                                "rerank_score": score,
                                "snippet": snippet,
                            })

                st.session_state.messages.append({
                    "role": "assistant",
                    "content": response,
                    "badge": badge,
                    "sources": sources,
                })

            except Exception as e:
                st.error(f"Error: {str(e)}")
