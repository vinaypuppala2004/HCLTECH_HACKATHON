"""Person A's Streamlit chat, calling the backend over HTTP."""

import httpx
import streamlit as st

from evidencedesk.contracts.models import Envelope, QueryInput, QueryResult, Scope
from evidencedesk.core.settings import get_settings


def show_reply(result: QueryResult) -> None:
    for claim in result.result.claims:
        st.write(claim.text)
    if not result.result.claims:
        st.write(result.result.fallback_reason or result.result.status)
    st.caption(f"Mode: {result.mode} | Evidence strength: {result.verification.evidence_strength}")
    with st.expander("Supporting evidence"):
        for hit in result.retrieval.hits:
            st.write(hit.document.metadata.title)
            st.caption(" / ".join(hit.passage.section_path))
            st.text(hit.passage.text)
            st.caption(f"Source: {hit.document.document_id} | {hit.document.metadata.origin}")


settings = get_settings()
st.set_page_config(page_title="EvidenceDesk", page_icon="📚")
st.title("EvidenceDesk")
st.warning(
    "MOCK MODE — every question returns the same sample passage. Live RAG is not implemented."
)
st.caption('Try: "How do I reset my password?"')

with st.sidebar:
    st.subheader("Question context")
    product = st.text_input("Product")
    version = st.text_input("Version")
    environment = st.text_input("Environment")
    st.caption("Context is sent to the API; the retrieval stub does not filter it yet.")

if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        if "result" in message:
            show_reply(QueryResult.model_validate(message["result"]))
        else:
            st.write(message["text"])

if question := st.chat_input("Ask about the documents", max_chars=2000):
    st.session_state.messages.append({"role": "user", "text": question})
    with st.chat_message("user"):
        st.write(question)
    with st.chat_message("assistant"):
        try:
            payload = QueryInput(
                question=question,
                context=Scope(
                    product=product.strip() or None,
                    version=version.strip() or None,
                    environment=environment.strip() or None,
                ),
            )
            with st.spinner("Requesting a mock reply..."):
                response = httpx.post(
                    f"{settings.backend_url}/v1/query",
                    json=payload.model_dump(),
                    timeout=30,
                    trust_env=False,
                )
                response.raise_for_status()
                envelope = Envelope[QueryResult].model_validate(response.json())
                if not envelope.ok or envelope.data is None:
                    raise ValueError("The backend returned an unsuccessful response.")
            result = envelope.data
            show_reply(result)
            st.session_state.messages.append({"role": "assistant", "result": result.model_dump()})
        except (httpx.HTTPError, ValueError) as exc:
            text = f"Could not get a reply. Start the FastAPI backend and retry. Details: {exc}"
            st.error(text)
            st.session_state.messages.append({"role": "assistant", "text": text})
