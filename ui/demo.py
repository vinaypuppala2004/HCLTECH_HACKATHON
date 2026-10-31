"""A5 panel-facing frontend presentation; run separately from the HTTP-backed app."""

import streamlit as st
from answers import show_answer
from conflicts import show_conflicts
from demo_examples import DemoExample, demo_examples


def load_example_context(examples: list[DemoExample]) -> None:
    example = next(item for item in examples if item.title == st.session_state.presentation_example)
    for field, value in example.query.context.model_dump().items():
        st.session_state[f"scope_{field}"] = value or ""


st.set_page_config(page_title="EvidenceDesk | Presentation preview", page_icon="📚", layout="wide")
st.title("EvidenceDesk")
st.subheader("Evidence before answers")
st.warning(
    "SYNTHETIC PRESENTATION PREVIEW — every example is fixed mock data. "
    "This is not a live query or a saved live result."
)
st.caption("No API, model, or index calls. No evaluation scores. The main app runs separately.")

examples = demo_examples()
selection = st.selectbox(
    "Presentation example",
    options=[example.title for example in examples],
    key="presentation_example",
    on_change=load_example_context,
    args=(examples,),
)
example = next(item for item in examples if item.title == selection)
for field, value in example.query.context.model_dump().items():
    st.session_state.setdefault(f"scope_{field}", value or "")

with st.sidebar:
    st.subheader("Context controls — preview only")
    st.text_input("Product", key="scope_product")
    st.text_input("Version", key="scope_version")
    st.text_input("Environment", key="scope_environment")
    st.caption(
        "Use this context fills these fields. Editing them does not change the fixed example "
        "or send a request. Use the main app to submit questions."
    )

st.write(f"Example question: {example.query.question}")
scope = example.query.context
st.caption(
    f"Example context — Product: {scope.product or 'Any'} | "
    f"Version: {scope.version or 'Any'} | Environment: {scope.environment or 'Any'}"
)
st.divider()
show_answer(example.result)
st.caption(f"Mode: {example.result.mode} | All sources: synthetic")
show_conflicts(example.result, key_prefix=f"presentation_{examples.index(example)}")

with st.expander("Presenter notes"):
    st.write(example.presenter_note)
with st.expander("Current implementation and limits"):
    st.write(
        "The main app calls FastAPI for live document Q&A when APP_MODE=live. "
        "Mock mode retains the fixed fixture and explicit NOT_IMPLEMENTED upload rejections."
    )
    st.write(
        "These presentation examples exercise frontend states only. Live ingestion, retrieval, "
        "Ollama inference, and Qdrant persistence are available in the main app. "
        "This preview remains synthetic. "
        "Measured Ragas evaluation and its report remain unimplemented."
    )
