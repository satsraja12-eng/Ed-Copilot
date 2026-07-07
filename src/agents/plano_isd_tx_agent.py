"""Plano ISD district agent — plugin hook stub.

Mirror of frisco_isd_tx_agent.py — follows the same structure so the
pattern is immediately clear.

The DistrictRegistry loads this automatically when it finds
config/tenants/plano-isd-tx.yaml pointing to this module.
"""
from __future__ import annotations

import os
from typing import List

from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from src.agents.base_agent import DistrictAgent

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
CHROMA_DIR = os.path.join(BASE_DIR, "chroma_db")

PERSONA_INSTRUCTIONS = {
    "student": "Explain simply. Use examples. Be encouraging.",
    "parent": "Give practical context. What should my child focus on?",
    "teacher": "Be precise. Give full detail.",
}

_DISCLAIMER = (
    "_This information was sourced from Plano ISD public resources. "
    "Verify at pisd.edu._"
)


def _get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        base_url=os.environ.get("NEBIUS_BASE_URL", "https://api.studio.nebius.ai/v1/"),
        api_key=os.environ.get("NEBIUS_API_KEY", ""),
        model="meta-llama/Llama-3.3-70B-Instruct",
    )


class PlanoIsdAgent(DistrictAgent):
    """Plano ISD course catalog + admin policy agent."""

    def __init__(self):
        self._embeddings = None
        self._vs_cache: dict = {}

    @property
    def district_id(self) -> str:
        return "plano_isd_tx"

    @property
    def supported_intents(self) -> List[str]:
        return ["course_catalog", "admin_policy"]

    def _get_vectorstore(self, doc_type: str):
        if doc_type in self._vs_cache:
            return self._vs_cache[doc_type]
        try:
            from langchain_chroma import Chroma
            from langchain_huggingface import HuggingFaceEmbeddings

            if self._embeddings is None:
                self._embeddings = HuggingFaceEmbeddings(model_name="BAAI/bge-small-en-v1.5")

            collection = f"plano_isd_tx__{doc_type}"
            vs = Chroma(
                collection_name=collection,
                persist_directory=CHROMA_DIR,
                embedding_function=self._embeddings,
            )
            self._vs_cache[doc_type] = vs
            return vs
        except Exception as exc:
            raise RuntimeError(
                f"Plano ISD ChromaDB collection '{doc_type}' not found. "
                f"Run ingestion first: src/ingestion/plano_ingestion.py\n({exc})"
            )

    def retrieve(self, query: str, intent: str, persona: str) -> List[Document]:
        doc_type_map = {
            "course_catalog": "course_catalog",
            "admin_policy": "admin_policy",
        }
        doc_type = doc_type_map.get(intent)
        if not doc_type:
            return []

        try:
            vs = self._get_vectorstore(doc_type)
            docs = vs.similarity_search(
                query,
                k=8,
                filter={"district": self.district_id, "doc_type": doc_type},
            )
            return [d for d in docs if d.metadata.get("district") == self.district_id]
        except RuntimeError as exc:
            print(f"[plano_agent] retrieve skipped — {exc}")
            return []

    def synthesize(
        self,
        query: str,
        docs: List[Document],
        intent: str,
        persona: str,
    ) -> str:
        if not docs:
            return (
                "I don't have Plano ISD course catalog data available yet. "
                "Ingestion for Plano ISD is scheduled for Phase 2.\n\n"
                + _DISCLAIMER
            )

        context = "\n\n".join(
            f"[{d.metadata.get('doc_title', 'document')} | {d.metadata.get('source_url', '')}]\n{d.page_content}"
            for d in docs
        )

        llm = _get_llm()
        prompt = ChatPromptTemplate.from_messages([
            ("system", (
                "You are a school assistant for Plano ISD families.\n"
                "{persona_instruction}\n"
                "Answer using ONLY the provided Plano ISD content below.\n"
                "If the context does not contain the answer, say "
                "'I don't have that specific Plano ISD information — please check pisd.edu.'\n"
                "Always end with: " + _DISCLAIMER + "\n\nContext:\n{context}"
            )),
            ("human", "{question}"),
        ])

        response = (prompt | llm | StrOutputParser()).invoke({
            "persona_instruction": PERSONA_INSTRUCTIONS.get(persona, PERSONA_INSTRUCTIONS["parent"]),
            "context": context,
            "question": query,
        })

        if _DISCLAIMER not in response:
            response = response.rstrip() + "\n\n" + _DISCLAIMER
        return response


# DistrictRegistry reads this variable automatically.
agent = PlanoIsdAgent()
