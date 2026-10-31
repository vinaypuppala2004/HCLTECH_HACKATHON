"""Person A's Streamlit chat, calling the backend over HTTP."""

import streamlit as st
from answers import show_answer
from chat_history import pending_replies, queue_question
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
        "MOCK MODE — every question returns the same sample passage. "
        "Choose live mode for your documents."
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
    st.caption("Context filters live retrieval. Mock mode ignores these values.")

if "messages" not in st.session_state:
    st.session_state.messages = []

st.chat_input(
    "Ask about the documents", max_chars=2000, key="chat_question", on_submit=queue_question
)

for message in pending_replies():
    try:
        payload = QueryInput.model_validate(message["query"])
        with st.spinner("Requesting a reply..."):
            result = request_query(settings.backend_url, payload)
            message.update(status="complete", result=result.model_dump())
    except (QueryServiceError, ValueError) as exc:
        text = (
            str(exc)
            if isinstance(exc, QueryServiceError)
            else "BAD_INPUT: Enter a question containing 1–2,000 non-whitespace characters."
        )
        message.update(status="error", text=text)

for message_index, message in enumerate(st.session_state.messages):
    with st.chat_message(message["role"]):
        if "result" in message:
            show_reply(
                QueryResult.model_validate(message["result"]), key_prefix=f"reply_{message_index}"
            )
        elif message.get("status") == "in_flight":
            st.warning(
                "REQUEST_INTERRUPTED: This request has no saved result and will not be sent again "
                "automatically. Submit the question again if you want a new request."
            )
        elif message["role"] == "assistant":
            st.error(message["text"])
        else:
            st.write(message["text"])
            if "context" in message:
                context = Scope.model_validate(message["context"])
                st.caption(
                    f"Submitted context — Product: {context.product or 'Any'} | "
                    f"Version: {context.version or 'Any'} | "
                    f"Environment: {context.environment or 'Any'}"
                )
