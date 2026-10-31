"""A1 upload controls and source browsing through the frozen document API."""

from base64 import b64encode
from collections.abc import Sequence
from pathlib import Path

import httpx
import streamlit as st
from streamlit.runtime.uploaded_file_manager import UploadedFile

from evidencedesk.contracts.models import (
    Envelope,
    IngestInput,
    IngestResult,
    Metadata,
    SourcesInput,
    SourcesResult,
    Upload,
)

UPLOAD_TYPES = ["pdf", "html", "htm", "md", "markdown", "txt"]
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_BATCH_BYTES = 50 * 1024 * 1024


def build_upload_request(files: Sequence[UploadedFile]) -> IngestInput:
    """Encode in memory, without saving uploads or adding scope controls."""
    if not 1 <= len(files) <= 20:
        raise ValueError("Select between 1 and 20 files.")
    if any(file.size > MAX_FILE_BYTES for file in files):
        raise ValueError("Each file must be at most 10 MB.")
    if sum(file.size for file in files) > MAX_BATCH_BYTES:
        raise ValueError("The upload batch must be at most 50 MB.")
    documents = []
    for file in files:
        if Path(file.name).suffix.lower().lstrip(".") not in UPLOAD_TYPES:
            raise ValueError(f"Unsupported file format: {file.name}")
        documents.append(
            Upload(
                filename=file.name,
                content_base64=b64encode(file.getvalue()).decode("ascii"),
                metadata=Metadata(
                    title=file.name,
                    source_url=None,
                    product=None,
                    version=None,
                    environment=None,
                    family_id=None,
                    published_at=None,
                    origin="user",
                ),
            )
        )
    return IngestInput(documents=documents)


def post_document_request[T](
    backend_url: str,
    route: str,
    payload: IngestInput | SourcesInput,
    result_type: type[T],
) -> T:
    response = httpx.post(
        f"{backend_url}{route}",
        json=payload.model_dump(),
        timeout=600,
        trust_env=False,
    )
    envelope = Envelope[result_type].model_validate(response.json())
    if envelope.error is not None:
        raise ValueError(
            f"{envelope.error.code}: {envelope.error.message} (request {envelope.request_id})"
        )
    response.raise_for_status()
    if not envelope.ok or envelope.data is None:
        raise ValueError("The backend returned an unsuccessful document response.")
    return envelope.data


def show_uploads(backend_url: str) -> None:
    st.subheader("Upload documents")
    st.caption("PDF, HTML, Markdown, or TXT. Up to 20 files; 10 MB each and 50 MB per batch.")
    st.info("Mock ingestion rejects uploads with NOT_IMPLEMENTED; it does not save or index files.")
    with st.form("document_upload"):
        files = st.file_uploader("Choose documents", type=UPLOAD_TYPES, accept_multiple_files=True)
        submitted = st.form_submit_button("Upload documents")
    if submitted:
        st.session_state.pop("a1_upload_result", None)
        try:
            payload = build_upload_request(files)
            with st.spinner("Submitting documents..."):
                result = post_document_request(
                    backend_url, "/v1/documents:ingest", payload, IngestResult
                )
            st.session_state.a1_upload_result = result.model_dump()
        except (httpx.HTTPError, ValueError) as exc:
            st.error(f"Could not upload documents. Details: {exc}")
    if "a1_upload_result" in st.session_state:
        result = IngestResult.model_validate(st.session_state.a1_upload_result)
        st.caption(f"Upload response — index revision: {result.index_revision}")
        for item in result.results:
            if item.state == "rejected":
                detail = (
                    f"{item.error.code}: {item.error.message}"
                    if item.error
                    else "No reason provided."
                )
                st.error(f"{item.filename}: rejected; not indexed. {detail}")
            else:
                if item.state == "ready":
                    st.success(f"{item.filename}: ready")
                else:
                    st.info(f"{item.filename}: duplicate; already indexed")
                st.caption(f"Document: {item.document_id} | Passages: {item.passage_count}")


def show_sources(backend_url: str) -> None:
    st.subheader("Browse sources")
    if st.button("Browse / refresh sources"):
        st.session_state.pop("a1_sources", None)
        st.session_state.pop("a1_source_details", None)
        try:
            with st.spinner("Loading sources..."):
                result = post_document_request(
                    backend_url, "/v1/sources:read", SourcesInput(document_id=None), SourcesResult
                )
            st.session_state.a1_sources = result.model_dump()
        except (httpx.HTTPError, ValueError) as exc:
            st.error(f"Could not list sources. Details: {exc}")
    if "a1_sources" not in st.session_state:
        st.caption("Browse sources to load the document list from the backend.")
        return
    sources = SourcesResult.model_validate(st.session_state.a1_sources)
    if not sources.documents:
        st.info("No documents are available.")
        return
    documents = {document.document_id: document for document in sources.documents}
    selected = st.selectbox(
        "Source document",
        options=list(documents),
        format_func=lambda document_id: (
            f"{documents[document_id].metadata.title} "
            f"({documents[document_id].filename}) [{document_id}]"
        ),
    )
    document = documents[selected]
    st.text(document.metadata.title)
    st.caption(
        f"Document: {document.document_id} | File: {document.filename} | "
        f"Format: {document.format} | Passages: {document.passage_count} | "
        f"Origin: {document.metadata.origin}"
    )
    if document.metadata.origin == "synthetic":
        st.warning("Synthetic fixture — this source is mock data.")
    if document.metadata.source_url:
        st.text(f"Source URL: {document.metadata.source_url}")
    if st.button("Open source"):
        st.session_state.pop("a1_source_details", None)
        try:
            with st.spinner("Loading passages..."):
                result = post_document_request(
                    backend_url,
                    "/v1/sources:read",
                    SourcesInput(document_id=selected),
                    SourcesResult,
                )
            st.session_state.a1_source_details = {
                "document_id": selected,
                "result": result.model_dump(),
            }
        except (httpx.HTTPError, ValueError) as exc:
            st.error(f"Could not read source. Details: {exc}")
    details = st.session_state.get("a1_source_details")
    if details is None or details["document_id"] != selected:
        return
    passages = SourcesResult.model_validate(details["result"]).passages
    if not passages:
        st.info("No passages are available for this source.")
    for passage in passages:
        st.caption(f"Document: {passage.document_id} | Passage: {passage.passage_id}")
        st.caption(" / ".join(passage.section_path) or "No section heading")
        if passage.page is not None:
            st.caption(f"Page: {passage.page}")
        st.text(passage.text)


def show_documents(backend_url: str) -> None:
    with st.expander("Documents"):
        show_uploads(backend_url)
        show_sources(backend_url)
