"""Synthetic B4 validation checks; no production index or model is used."""

import base64
from dataclasses import replace
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from evidencedesk.api.app import create_app
from evidencedesk.contracts.models import (
    Envelope,
    IngestInput,
    IngestResult,
    Metadata,
    ToolError,
    Upload,
)
from evidencedesk.core.factory import build_tools
from evidencedesk.core.settings import Settings
from evidencedesk.ingestion import batching
from evidencedesk.ingestion.batching import prepare_uploads
from evidencedesk.ingestion.chunking import ChunkingConfig, prepare_document
from evidencedesk.ingestion.tools import ingest_documents, validate_documents


@pytest.fixture
def upload():
    def make(filename="synthetic.txt", content=b"Synthetic evidence.", *, encoded=None):
        return Upload(
            filename=filename,
            content_base64=base64.b64encode(content).decode("ascii")
            if encoded is None
            else encoded,
            metadata=Metadata(
                title="Synthetic guide",
                source_url=None,
                product=None,
                version=None,
                environment=None,
                family_id=None,
                published_at=None,
                origin="synthetic",
            ),
        )

    return make


@pytest.fixture
def pdf_bytes():
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
    )
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 72 720 Td (Synthetic PDF evidence.) Tj ET")
    page[NameObject("/Contents")] = stream
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_valid_formats_prepare_contract_records_in_input_order(upload, pdf_bytes):
    records = [
        upload("synthetic.md", b"# Guide\nMarkdown evidence."),
        upload("synthetic.html", b"<h1>Guide</h1><p>HTML evidence.</p>"),
        upload("synthetic.txt", "Synthetic café evidence.".encode()),
        upload("synthetic.pdf", pdf_bytes),
    ]
    batch = prepare_uploads(IngestInput(documents=records))
    assert [item.filename for item in batch.uploads] == [record.filename for record in records]
    assert [item.document.format for item in batch.documents] == ["markdown", "html", "txt", "pdf"]
    assert batch.decoded_bytes == sum(
        len(base64.b64decode(item.content_base64)) for item in records
    )
    assert batch.passage_count == sum(len(item.passages) for item in batch.documents)
    assert batch.documents[3].passages[0].page == 1
    assert all(item.document.metadata.origin == "synthetic" for item in batch.documents)


@pytest.mark.parametrize(
    "encoded",
    [
        "%%%",
        "SGVsbG8",
        "SGVsbG8=\n",
        "SGVs bG8=",
        "SGVsbG8===",
        "🙂",
        "data:text/plain;base64,QQ==",
    ],
)
def test_malformed_base64_is_a_per_file_error(upload, encoded):
    batch = prepare_uploads(IngestInput(documents=[upload(encoded=encoded), upload("other.txt")]))
    assert isinstance(batch.uploads[0].value, ToolError)
    assert batch.uploads[0].value.code == "BAD_INPUT"
    assert batch.uploads[0].value.message == "content_base64 must be strict, padded base64."
    assert len(batch.documents) == 1
    assert batch.documents[0].document.filename == "other.txt"


@pytest.mark.parametrize(
    ("filename", "content", "code"),
    [
        ("empty.txt", b"", "EMPTY_DOCUMENT"),
        ("empty.md", b" \n\t", "EMPTY_DOCUMENT"),
        ("empty.html", b"<script>hidden</script>", "EMPTY_DOCUMENT"),
        ("corrupt.pdf", b"not a PDF", "BAD_INPUT"),
        ("invalid.txt", b"invalid \xff", "BAD_INPUT"),
        ("nul.txt", b"text\x00content", "BAD_INPUT"),
        ("unsupported.docx", b"Synthetic evidence.", "UNSUPPORTED_FORMAT"),
    ],
)
def test_document_failures_do_not_block_other_files(upload, filename, content, code):
    batch = prepare_uploads(IngestInput(documents=[upload(filename, content), upload("good.txt")]))
    assert batch.uploads[0].value.code == code
    assert len(batch.documents) == 1
    assert batch.documents[0].document.filename == "good.txt"


def test_mixed_failures_preserve_original_order_and_file_association(upload):
    records = [
        upload("good.txt"),
        upload("empty.txt", b""),
        upload("corrupt.pdf", b"bad"),
        upload("unsupported.exe"),
        upload("bad-base64.txt", encoded="!"),
        upload("good.html", b"<p>Other evidence.</p>"),
    ]
    batch = prepare_uploads(IngestInput(documents=records))
    assert [item.filename for item in batch.uploads] == [item.filename for item in records]
    assert [item.value.code for item in batch.uploads if isinstance(item.value, ToolError)] == [
        "EMPTY_DOCUMENT",
        "BAD_INPUT",
        "UNSUPPORTED_FORMAT",
        "BAD_INPUT",
    ]
    assert [item.document.filename for item in batch.documents] == ["good.txt", "good.html"]


def test_duplicate_filenames_and_bytes_remain_separate_without_claiming_deduplication(upload):
    record = upload("same-name.txt")
    batch = prepare_uploads(IngestInput(documents=[record, record]))
    assert len(batch.uploads) == len(batch.documents) == 2
    assert batch.documents[0].document.document_id == batch.documents[1].document.document_id
    response = validate_documents(IngestInput(documents=[record, record]))
    assert [item.state for item in response.data.results] == ["rejected", "rejected"]


@pytest.mark.parametrize("size", [10, 11, 12, 13])
def test_file_limit_checks_exact_decoded_size_even_at_same_encoded_length(
    upload, monkeypatch, size
):
    monkeypatch.setattr(batching, "MAX_FILE_BYTES", 10)
    batch = prepare_uploads(IngestInput(documents=[upload(content=b"x" * size)]))
    if size == 10:
        assert len(batch.documents) == 1
        assert batch.decoded_bytes == 10
    else:
        assert not batch.documents
        assert batch.uploads[0].value.code == "BAD_INPUT"
        assert "10 MB" in batch.uploads[0].value.message


def test_oversized_encoded_input_is_rejected_before_decoding(upload, monkeypatch):
    monkeypatch.setattr(batching, "MAX_FILE_BYTES", 10)

    def unexpected_decode(*args, **kwargs):
        raise AssertionError("Oversized input must not be decoded")

    monkeypatch.setattr(batching.base64, "b64decode", unexpected_decode)
    batch = prepare_uploads(IngestInput(documents=[upload(encoded="A" * 20)]))
    assert batch.uploads[0].value.code == "BAD_INPUT"
    assert not batch.documents


def test_batch_limit_allows_exact_decoded_boundary(upload, monkeypatch):
    monkeypatch.setattr(batching, "MAX_BATCH_BYTES", 20)
    batch = prepare_uploads(
        IngestInput(documents=[upload(content=b"x" * 10), upload(content=b"y" * 10)])
    )
    assert batch.decoded_bytes == 20
    assert len(batch.documents) == 2


def test_oversized_batch_never_reaches_parsing_and_retains_individual_errors(upload, monkeypatch):
    monkeypatch.setattr(batching, "MAX_BATCH_BYTES", 20)

    def unexpected_prepare(*args, **kwargs):
        raise AssertionError("No file in an oversized batch may be prepared")

    monkeypatch.setattr(batching, "prepare_document", unexpected_prepare)
    batch = prepare_uploads(
        IngestInput(
            documents=[
                upload(encoded="!"),
                upload(content=b"x" * 10),
                upload(content=b"y" * 11),
                upload("later.txt", b"later"),
                upload("later-bad.txt", encoded="!"),
            ]
        )
    )
    assert batch.decoded_bytes == 26
    assert batch.passage_count == 0 and not batch.documents
    assert all(isinstance(item.value, ToolError) for item in batch.uploads)
    assert "strict, padded base64" in batch.uploads[0].value.message
    assert "50 MB" in batch.uploads[1].value.message
    assert "50 MB" in batch.uploads[3].value.message
    assert "strict, padded base64" in batch.uploads[4].value.message


def test_decoded_budget_counts_bytes_not_unicode_characters(upload):
    batch = prepare_uploads(IngestInput(documents=[upload(content="é🙂".encode())]))
    assert batch.decoded_bytes == 6
    assert batch.documents[0].passages[0].text == "é🙂"


@pytest.mark.parametrize("second_size", [250, 251])
def test_batch_passage_limit_discards_prepared_results_on_overflow(upload, second_size):
    request = IngestInput(
        documents=[upload("first.txt", b"x" * 250), upload("second.txt", b"y" * second_size)]
    )
    batch = prepare_uploads(request, config=ChunkingConfig(1, 0))
    if second_size == 250:
        assert batch.passage_count == 500 and len(batch.documents) == 2
    else:
        assert batch.passage_count == 0 and not batch.documents
        assert all(item.value.code == "BAD_INPUT" for item in batch.uploads)
        assert all("500 passages" in item.value.message for item in batch.uploads)


def test_file_chunk_limit_is_per_file_and_other_files_can_still_prepare(upload):
    request = IngestInput(documents=[upload("too-many.txt", b"x" * 501), upload("good.txt", b"y")])
    batch = prepare_uploads(request, config=ChunkingConfig(1, 0))
    assert batch.uploads[0].value.code == "BAD_INPUT"
    assert len(batch.documents) == 1
    assert batch.documents[0].document.filename == "good.txt"


def test_unexpected_file_failure_is_generic_and_later_files_continue(upload, monkeypatch):
    original = batching.prepare_document

    def fail_one(filename, *args, **kwargs):
        if filename == "broken.txt":
            raise RuntimeError("Synthetic private failure detail")
        return original(filename, *args, **kwargs)

    monkeypatch.setattr(batching, "prepare_document", fail_one)
    batch = prepare_uploads(IngestInput(documents=[upload("broken.txt"), upload("good.txt")]))
    assert batch.uploads[0].value.code == "INTERNAL_ERROR"
    assert batch.uploads[0].value.message == "Unexpected document preparation error."
    assert batch.uploads[0].value.retryable is False
    assert len(batch.documents) == 1


def test_prepared_warnings_are_retained_for_future_indexing_handoff(upload, monkeypatch):
    record = upload()
    prepared = prepare_document(record.filename, b"Synthetic evidence.", record.metadata)
    warned = replace(prepared, warnings=("Synthetic parser warning.",))
    monkeypatch.setattr(batching, "prepare_document", lambda *args, **kwargs: warned)
    batch = prepare_uploads(IngestInput(documents=[record]))
    assert batch.documents[0].warnings == ("Synthetic parser warning.",)


def test_validation_tool_uses_frozen_envelope_and_never_claims_indexing(upload):
    response = validate_documents(IngestInput(documents=[upload(), upload("empty.txt", b"")]))
    validated = Envelope[IngestResult].model_validate_json(response.model_dump_json())
    assert validated.ok and validated.error is None
    assert validated.data.index_revision == 0
    assert [item.error.code for item in validated.data.results] == [
        "NOT_IMPLEMENTED",
        "EMPTY_DOCUMENT",
    ]
    for item in validated.data.results:
        assert item.state == "rejected"
        assert item.document_id is None and item.passage_count == 0
    assert "Nothing was indexed" in validated.data.results[0].error.message


def test_default_mock_ingestion_is_preserved(upload):
    response = ingest_documents(IngestInput(documents=[upload(encoded="not base64!")]))
    assert response.data.index_revision == 1
    assert response.data.results[0].error.code == "NOT_IMPLEMENTED"


def test_existing_api_accepts_injected_validation_tool_with_http_200_per_file_errors(upload):
    settings = Settings()
    tools = replace(build_tools(settings), ingest=validate_documents)
    records = [upload(), upload("empty.txt", b""), upload("bad.pdf", b"not a PDF")]
    request = IngestInput(documents=records)
    with TestClient(create_app(settings, tools=tools)) as client:
        before = client.get("/v1/health").json()["data"]
        response = client.post("/v1/documents:ingest", json=request.model_dump(mode="json"))
        assert response.status_code == 200
        result = Envelope[IngestResult].model_validate(response.json())
        assert result.ok and result.error is None
        assert [item.error.code for item in result.data.results] == [
            "NOT_IMPLEMENTED",
            "EMPTY_DOCUMENT",
            "BAD_INPUT",
        ]
        after = client.get("/v1/health").json()["data"]
        assert before == after
        listed = client.post("/v1/sources:read", json={"document_id": None}).json()
        assert [document["document_id"] for document in listed["data"]["documents"]] == [
            "doc_mock_guide"
        ]
        prepared_id = (
            prepare_uploads(IngestInput(documents=[records[0]])).documents[0].document.document_id
        )
        missing = client.post("/v1/sources:read", json={"document_id": prepared_id})
        assert missing.status_code == 404
