"""A4 session-local submissions and display-only history."""

from collections.abc import Iterator

import streamlit as st


def queue_question() -> None:
    """Capture a new chat-input event and its scope, including deliberate repeats."""
    question = st.session_state.get("chat_question")
    if question is None:
        return
    context = {
        field: st.session_state.get(f"scope_{field}", "").strip() or None
        for field in ("product", "version", "environment")
    }
    st.session_state.setdefault("messages", []).extend(
        [
            {"role": "user", "text": question, "context": context.copy()},
            {
                "role": "assistant",
                "status": "queued",
                "query": {"question": question, "context": context},
            },
        ]
    )


def pending_replies() -> Iterator[dict]:
    """Consume each queued submission before HTTP; interrupted calls are not replayed."""
    for message in st.session_state.messages:
        if message.get("status") == "queued":
            message["status"] = "in_flight"
            yield message
