import streamlit as st
from src.retrieval import get_hybrid_retriever
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

st.set_page_config(page_title="NC Math RAG Tutor", page_icon="📚", layout="centered")

st.title("📚 NC Math Student & Parent Tutor")
st.markdown("Ask any question about the North Carolina Math 1, 2, or 3 curriculum!")

@st.cache_resource(show_spinner="Initializing Retrieval Pipeline...")
def init_retriever():
    return get_hybrid_retriever()

retriever = init_retriever()

# Initialize Nebius LLM (Llama-3-70B)
def get_llm():
    api_key = os.environ.get("NEBIUS_API_KEY")
    if not api_key or api_key == "your-key-here" or api_key == "":
        st.error("Please add your NEBIUS_API_KEY to the .env file.")
        st.stop()
        
    return ChatOpenAI(
        base_url=os.environ.get("NEBIUS_BASE_URL", "https://api.studio.nebius.ai/v1/"),
        api_key=api_key,
        model="meta-llama/Llama-3.3-70B-Instruct"
    )

llm = get_llm()

# Define the Persona Prompt
prompt_template = ChatPromptTemplate.from_messages([
    ("system", """You are a Patient Math Tutor for Wake County students and parents. 
    Answer the following question using ONLY the provided educational standards context. 
    Explain the concepts simply so a student or parent can understand.
    Do not use outside knowledge. 
    If the context does not contain the answer, say 'I cannot find this in our syllabus, please ask your teacher.'
    
    Context:
    {context}
    """),
    ("human", "{question}")
])

# Chat State
if "messages" not in st.session_state:
    st.session_state.messages = []

# Render chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# User Input
if prompt := st.chat_input("Ask a math question (e.g. What is standard NC.M3.F-IF.4 about?)..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Searching the syllabus..."):
            docs = retriever.invoke(prompt)
            context = "\n\n".join([f"[{doc.metadata.get('standard_id')}] {doc.page_content}" for doc in docs])
            
        with st.spinner("Thinking..."):
            try:
                chain = prompt_template | llm | StrOutputParser()
                response = chain.invoke({"context": context, "question": prompt})
                
                st.markdown(response)
                
                # Show sources
                with st.expander("View Retrieved Sources"):
                    for doc in docs:
                        st.write(f"**{doc.metadata.get('standard_id')}** (Course: {doc.metadata.get('course_id')}) - Rerank Score: {doc.metadata.get('rerank_score', 0):.2f}")
                        st.caption(doc.page_content[:300] + "...")
                        
                st.session_state.messages.append({"role": "assistant", "content": response})
            except Exception as e:
                st.error(f"Error generating response: {str(e)}")
