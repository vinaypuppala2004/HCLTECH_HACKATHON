"""A2 compares conflict sides without changing the backend's resolution."""

import streamlit as st

from evidencedesk.contracts.models import Metadata, QueryResult


def use_source_context(metadata: Metadata) -> None:
    """Fill the controls for the next question; do not submit or resolve anything."""
    st.session_state.scope_product = metadata.product or ""
    st.session_state.scope_version = metadata.version or ""
    st.session_state.scope_environment = metadata.environment or ""


def show_conflicts(result: QueryResult, *, key_prefix: str) -> None:
    if not result.result.conflicts:
        return
    st.subheader("Conflicting evidence")
    hits = {hit.passage.passage_id: hit for hit in result.retrieval.hits}
    for conflict_index, conflict in enumerate(result.result.conflicts):
        st.text(conflict.topic)
        st.caption(f"Conflict: {conflict.conflict_id} | Kind: {conflict.kind}")
        if conflict.resolution == "unresolved":
            st.warning("Unresolved conflict — the backend has not selected a resolution.")
        else:
            st.info("Resolved by context — the backend selected the marked passage(s).")
        selected = set(conflict.selected_passage_ids)
        for start in range(0, len(conflict.sides), 2):
            columns = st.columns(2)
            for side_index in range(start, min(start + 2, len(conflict.sides))):
                support = conflict.sides[side_index]
                hit = hits.get(support.passage_id)
                with columns[side_index - start]:
                    st.write(f"Side {side_index + 1}")
                    st.caption(f"Passage: {support.passage_id}")
                    if support.passage_id in selected:
                        st.caption("Selected by backend")
                    if hit is not None:
                        metadata = hit.document.metadata
                        st.text(metadata.title)
                        st.caption(
                            f"Product: {metadata.product or 'Not specified'} | "
                            f"Version: {metadata.version or 'Not specified'} | "
                            f"Environment: {metadata.environment or 'Not specified'}"
                        )
                        st.caption(f"Source: {hit.document.document_id} | {metadata.origin}")
                        st.caption(" / ".join(hit.passage.section_path) or "No section heading")
                        if hit.passage.page is not None:
                            st.caption(f"Page: {hit.passage.page}")
                        st.caption(
                            "API applicability: "
                            + ("applicable" if hit.applicable else "not applicable")
                        )
                        if metadata.origin == "synthetic":
                            st.caption("Synthetic fixture — mock evidence")
                    else:
                        st.warning("Source metadata is unavailable for this passage.")
                    st.text(support.quote)
                    if hit is not None:
                        st.button(
                            "Use this context",
                            key=f"{key_prefix}_conflict_{conflict_index}_side_{side_index}",
                            on_click=use_source_context,
                            args=(hit.document.metadata,),
                            help="Fill the context controls, then submit your question again.",
                        )
        st.caption(
            "Context changes apply to your next question. Submit it again to request "
            "an updated answer; only the backend can resolve this conflict."
        )
