"""Person A's Streamlit chat, calling the backend over HTTP."""

import streamlit as st
from answers import show_answer
from conflicts import show_conflicts
from documents import show_documents
from query_client import QueryServiceError, request_query

from evidencedesk.contracts.models import QueryInput, QueryResult, Scope
from evidencedesk.core.settings import get_settings


def show_reply(result: QueryResult, *, key_prefix: str) -> None:
    show_answer(result)
    st.caption(f"Mode: {result.mode} | Evidence strength: {result.verification.evidence_strength}")
    show_conflicts(result, key_prefix=key_prefix)
    with st.expander("Supporting evidence"):
        for hit in result.retrieval.hits:
            st.write(hit.document.metadata.title)
            st.caption(" / ".join(hit.passage.section_path))
            st.text(hit.passage.text)
            st.caption(f"Source: {hit.document.document_id} | {hit.document.metadata.origin}")


settings = get_settings()
st.set_page_config(page_title="EvidenceDesk", page_icon="📚")
st.title("EvidenceDesk")
if settings.app_mode == "mock":
    st.warning(
        "MOCK MODE — every question returns the same sample passage. Live RAG is not implemented."
    )
else:
    st.caption(f"Configured mode: {settings.app_mode}")
st.caption('Try: "How do I reset my password?"')

show_documents(settings.backend_url)

with st.sidebar:
    st.subheader("Question context")
    product = st.text_input(
        "Product", key="scope_product", help="Leave blank to send no product restriction."
    )
    version = st.text_input(
        "Version", key="scope_version", help="Use the exact version identifier, or leave blank."
    )
    environment = st.text_input(
        "Environment",
        key="scope_environment",
        help="Leave blank to send no environment restriction.",
    )
    st.caption("These values apply to your next question. Blank fields are sent as null.")
    st.caption("Context is sent to the API; the retrieval stub does not filter it yet.")

if "messages" not in st.session_state:
    st.session_state.messages = []

for message_index, message in enumerate(st.session_state.messages):
    with st.chat_message(message["role"]):
        if "result" in message:
            show_reply(
                QueryResult.model_validate(message["result"]), key_prefix=f"reply_{message_index}"
            )
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
            with st.spinner("Requesting a reply..."):
                result = request_query(settings.backend_url, payload)
            show_reply(result, key_prefix=f"reply_{len(st.session_state.messages)}")
            st.session_state.messages.append({"role": "assistant", "result": result.model_dump()})
        except (QueryServiceError, ValueError) as exc:
            text = (
                str(exc)
                if isinstance(exc, QueryServiceError)
                else "BAD_INPUT: Enter a question containing 1–2,000 non-whitespace characters."
            )
            st.error(text)
            st.session_state.messages.append({"role": "assistant", "text": text})
