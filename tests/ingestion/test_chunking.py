"""B3 checks with explicitly synthetic text/PDFs; no index or model is used."""

import hashlib
import json
import os
import random
import subprocess
import sys
from io import BytesIO

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from evidencedesk.contracts.models import (
    DraftInput,
    Hit,
    Metadata,
    QueryInput,
    Scope,
    SearchResult,
    VerifyInput,
)
from evidencedesk.ingestion.chunking import ChunkingConfig, chunk_document, prepare_document
from evidencedesk.ingestion.parsers import (
    DocumentParseError,
    ParsedDocument,
    SourceBlock,
    parse_document,
)


@pytest.fixture
def metadata():
    return Metadata(
        title="Synthetic guide",
        source_url=None,
        product="SyntheticDesk",
        version="1",
        environment="test",
        family_id="synthetic-guide",
        published_at=None,
        origin="synthetic",
    )


def text_document(text: str, *, start_line: int = 1) -> ParsedDocument:
    return ParsedDocument("synthetic.txt", "txt", (SourceBlock(text, start_line=start_line),))


def test_preparation_returns_existing_contract_models_and_raw_hash(metadata):
    content = "Synthetic café evidence.\r\nSecond line.".encode()
    prepared = prepare_document("synthetic.txt", content, metadata)
    assert prepared.document.sha256 == hashlib.sha256(content).hexdigest()
    assert prepared.document.filename == "synthetic.txt"
    assert prepared.document.format == "txt"
    assert prepared.document.metadata == metadata
    assert prepared.document.passage_count == len(prepared.passages) == 1
    assert prepared.passages[0].text == "Synthetic café evidence.\nSecond line."
    assert prepared.passages[0].document_id == prepared.document.document_id
    assert set(prepared.passages[0].model_dump()) == {
        "passage_id",
        "document_id",
        "section_path",
        "page",
        "text",
    }
    assert prepared.warnings == ()


def test_character_windows_have_exact_overlap_and_reconstruct_source():
    text = "0123456789ABCDEFGHIJ"
    chunks = chunk_document(text_document(text), "doc_test", config=ChunkingConfig(8, 3))
    assert [(chunk.start_offset, chunk.end_offset) for chunk in chunks] == [
        (0, 8),
        (5, 13),
        (10, 18),
        (15, 20),
    ]
    for left, right in zip(chunks, chunks[1:]):
        assert left.passage.text[-3:] == right.passage.text[:3]
    reconstructed = chunks[0].passage.text + "".join(chunk.passage.text[3:] for chunk in chunks[1:])
    assert reconstructed == text


@pytest.mark.parametrize(
    ("text", "max_chars", "expected_first"),
    [
        ("Paragraph one ends.\n\nParagraph two is much longer.", 30, "Paragraph one ends.\n\n"),
        ("abcdefghijklmno\nA second line is longer still.", 25, "abcdefghijklmno\n"),
        ("alpha beta gamma delta epsilon", 20, "alpha beta gamma "),
        ("abcdefghijklmnop", 8, "abcdefgh"),
    ],
)
def test_preferred_boundaries_and_unbroken_word_fallback(text, max_chars, expected_first):
    chunks = chunk_document(text_document(text), "doc_test", config=ChunkingConfig(max_chars, 3))
    assert chunks[0].passage.text == expected_first
    assert all(0 < len(chunk.passage.text) <= max_chars for chunk in chunks)


def test_zero_overlap_preserves_all_text():
    text = "Synthetic first sentence.\nSecond sentence with more evidence."
    chunks = chunk_document(text_document(text), "doc_test", config=ChunkingConfig(15, 0))
    assert "".join(chunk.passage.text for chunk in chunks) == text
    assert all(left.end_offset == right.start_offset for left, right in zip(chunks, chunks[1:]))


def test_single_character_size_and_near_full_overlap_terminate():
    text = "abcdefghij"
    single = chunk_document(text_document(text), "doc_test", config=ChunkingConfig(1, 0))
    overlapping = chunk_document(text_document(text), "doc_test", config=ChunkingConfig(5, 4))
    assert [chunk.passage.text for chunk in single] == list(text)
    assert [chunk.start_offset for chunk in overlapping] == list(range(6))
    assert overlapping[-1].passage.text == "fghij"


def test_varied_inputs_preserve_nonblank_characters_offsets_and_bounds():
    rng = random.Random(2026)
    alphabet = "abcXYZé🙂 \n\t"
    for _ in range(100):
        text = "E" + "".join(rng.choice(alphabet) for _ in range(rng.randrange(1, 100)))
        size = rng.randrange(1, 35)
        overlap = rng.randrange(size)
        chunks = chunk_document(
            text_document(text), "doc_test", config=ChunkingConfig(size, overlap)
        )
        covered = set()
        for chunk in chunks:
            assert chunk.passage.text == text[chunk.start_offset : chunk.end_offset]
            assert chunk.passage.text.strip()
            assert len(chunk.passage.text) <= size
            chunk.passage.text.encode("utf-8").decode("utf-8")
            covered.update(range(chunk.start_offset, chunk.end_offset))
        assert all(
            index in covered for index, character in enumerate(text) if not character.isspace()
        )
        assert all(
            left.start_offset < right.start_offset for left, right in zip(chunks, chunks[1:])
        )
        assert len({chunk.passage.passage_id for chunk in chunks}) == len(chunks)


def test_short_block_is_not_padded_or_rewritten():
    text = "  Exact synthetic evidence.\n"
    chunks = chunk_document(text_document(text), "doc_test")
    assert len(chunks) == 1
    assert chunks[0].passage.text == text
    assert (chunks[0].start_offset, chunks[0].end_offset) == (0, len(text))


def test_whitespace_windows_are_omitted_without_losing_evidence():
    text = "First" + " " * 100 + "Last"
    chunks = chunk_document(text_document(text), "doc_test", config=ChunkingConfig(10, 2))
    assert all(chunk.passage.text.strip() for chunk in chunks)
    assert chunks[0].passage.text.startswith("First")
    assert chunks[-1].passage.text.endswith("Last")


def test_markdown_heading_boundaries_and_exact_source_slices(metadata):
    content = (
        b"# Synthetic guide\nIntroductory evidence.\n\n"
        b"## Reset\nUse reset.\n\n## Access\nAsk support.\n"
    )
    parsed = parse_document("synthetic.md", content)
    prepared = prepare_document("synthetic.md", content, metadata, config=ChunkingConfig(25, 5))
    assert {tuple(passage.section_path) for passage in prepared.passages} == {
        ("Synthetic guide",),
        ("Synthetic guide", "Reset"),
        ("Synthetic guide", "Access"),
    }
    for chunk in prepared.chunks:
        block = parsed.blocks[chunk.block_index]
        assert chunk.passage.text == block.text[chunk.start_offset : chunk.end_offset]
        assert chunk.passage.section_path == list(block.section_path)
        assert chunk.passage.page is None
        assert block.start_line <= chunk.start_line <= chunk.end_line <= block.end_line
    assert all(
        "reset" not in chunk.passage.text.lower()
        for chunk in prepared.chunks
        if chunk.block_index == 0
    )


def test_source_line_ranges_are_precise_for_text_slices():
    parsed = text_document("line1\nline2\nline3\n", start_line=7)
    chunks = chunk_document(parsed, "doc_test", config=ChunkingConfig(6, 0))
    assert [chunk.passage.text for chunk in chunks] == ["line1\n", "line2\n", "line3\n"]
    assert [(chunk.start_line, chunk.end_line) for chunk in chunks] == [(7, 7), (8, 8), (9, 9)]


def test_html_chunks_keep_enclosing_markup_line_range(metadata):
    content = b"<h1>Guide</h1>\n<p>Alpha words\nBeta words\nGamma words</p>"
    prepared = prepare_document("synthetic.html", content, metadata, config=ChunkingConfig(12, 2))
    body = [chunk for chunk in prepared.chunks if chunk.block_index == 1]
    assert len(body) > 1
    assert all((chunk.start_line, chunk.end_line) == (2, 4) for chunk in body)
    assert all(chunk.passage.section_path == ["Guide"] for chunk in body)
    assert all(chunk.passage.page is None for chunk in prepared.chunks)


def test_adjacent_blocks_are_never_merged_even_with_same_heading():
    parsed = ParsedDocument(
        "synthetic.html",
        "html",
        (SourceBlock("First paragraph.", ("Guide",)), SourceBlock("Second paragraph.", ("Guide",))),
    )
    chunks = chunk_document(parsed, "doc_test", config=ChunkingConfig(100, 20))
    assert [chunk.passage.text for chunk in chunks] == ["First paragraph.", "Second paragraph."]
    assert [chunk.block_index for chunk in chunks] == [0, 1]


def test_real_pdf_preparation_preserves_pages_and_warnings(metadata):
    writer = PdfWriter()
    for text in ["First page evidence is long enough to split.", None, "Third page evidence."]:
        page = writer.add_blank_page(width=612, height=792)
        if text is None:
            continue
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
        stream.set_data(f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode())
        page[NameObject("/Contents")] = stream
    output = BytesIO()
    writer.write(output)
    prepared = prepare_document(
        "synthetic.pdf", output.getvalue(), metadata, config=ChunkingConfig(20, 4)
    )
    assert {passage.page for passage in prepared.passages} == {1, 3}
    assert len([passage for passage in prepared.passages if passage.page == 1]) > 1
    assert all(chunk.start_line is None and chunk.end_line is None for chunk in prepared.chunks)
    assert all(passage.section_path == [] for passage in prepared.passages)
    assert prepared.warnings == ("Page 2 has no extractable text; OCR is not supported.",)


def test_ids_are_stable_across_repeated_calls_and_file_renames(metadata):
    first = prepare_document("synthetic.md", b"# Guide\nEvidence.", metadata)
    repeated = prepare_document("synthetic.md", b"# Guide\nEvidence.", metadata)
    renamed = prepare_document("renamed.MARKDOWN", b"# Guide\nEvidence.", metadata)
    assert first == repeated
    assert renamed.document.document_id == first.document.document_id
    assert renamed.document.filename == "renamed.MARKDOWN"
    assert renamed.passages == first.passages


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("title", "Other synthetic title"),
        ("source_url", "https://example.invalid/synthetic.txt"),
        ("product", "OtherSyntheticDesk"),
        ("version", "2"),
        ("environment", "other-test"),
        ("family_id", "other-synthetic-guide"),
        ("published_at", "2026-10-31"),
        ("origin", "user"),
    ],
)
def test_source_metadata_distinguishes_document_and_passage_ids(metadata, field, value):
    first = prepare_document("synthetic.txt", b"Same synthetic bytes.", metadata)
    changed = prepare_document(
        "synthetic.txt", b"Same synthetic bytes.", metadata.model_copy(update={field: value})
    )
    assert first.document.sha256 == changed.document.sha256
    assert first.document.document_id != changed.document.document_id
    assert first.passages[0].passage_id != changed.passages[0].passage_id


def test_raw_content_and_format_changes_distinguish_ids(metadata):
    first = prepare_document("synthetic.txt", b"Evidence.\n", metadata)
    newline_changed = prepare_document("synthetic.txt", b"Evidence.\r\n", metadata)
    format_changed = prepare_document("synthetic.md", b"Evidence.\n", metadata)
    assert first.passages[0].text == newline_changed.passages[0].text
    assert (
        len({item.document.document_id for item in [first, newline_changed, format_changed]}) == 3
    )


def test_chunk_policy_changes_passage_spans_without_changing_document_id(metadata):
    content = b"abcdefghijklmnopqrstuvwxyz" * 4
    first = prepare_document("synthetic.txt", content, metadata, config=ChunkingConfig(20, 4))
    changed = prepare_document("synthetic.txt", content, metadata, config=ChunkingConfig(25, 4))
    assert first.document.document_id == changed.document.document_id
    assert first.passages[0].passage_id != changed.passages[0].passage_id


def test_repeated_identical_blocks_have_distinct_passage_ids():
    block = SourceBlock("Repeated synthetic evidence.", ("Guide",))
    parsed = ParsedDocument("synthetic.html", "html", (block, block))
    chunks = chunk_document(parsed, "doc_test")
    assert chunks[0].passage.text == chunks[1].passage.text
    assert chunks[0].passage.passage_id != chunks[1].passage.passage_id


def test_metadata_snapshot_does_not_change_if_caller_mutates_metadata(metadata):
    prepared = prepare_document("synthetic.txt", b"Synthetic evidence.", metadata)
    metadata.version = "changed-after-preparation"
    assert prepared.document.metadata.version == "1"


def test_ids_do_not_depend_on_python_hash_seed():
    script = """
import json
from evidencedesk.contracts.models import Metadata
from evidencedesk.ingestion.chunking import prepare_document
metadata = Metadata(title="Synthetic", source_url=None, product=None, version=None,
    environment=None, family_id=None, published_at=None, origin="synthetic")
result = prepare_document("synthetic.txt", b"Stable synthetic evidence.", metadata)
print(json.dumps([result.document.document_id, result.passages[0].passage_id]))
"""
    outputs = [
        subprocess.check_output(
            [sys.executable, "-c", script], env={**os.environ, "PYTHONHASHSEED": seed}, text=True
        ).strip()
        for seed in ["1", "42"]
    ]
    assert json.loads(outputs[0]) == json.loads(outputs[1])


@pytest.mark.parametrize(
    ("max_chars", "overlap_chars"),
    [
        (0, 0),
        (-1, 0),
        (True, 0),
        (1.5, 0),
        ("10", 0),
        (10, -1),
        (10, 10),
        (10, 11),
        (10, True),
        (10, 1.5),
        (10, "2"),
    ],
)
def test_invalid_configuration_fails_early(max_chars, overlap_chars):
    with pytest.raises(ValueError):
        ChunkingConfig(max_chars, overlap_chars)


@pytest.mark.parametrize("document_id", ["", " \t\n"])
def test_blank_document_id_is_rejected(document_id):
    with pytest.raises(ValueError, match="nonblank"):
        chunk_document(text_document("Synthetic evidence."), document_id)


@pytest.mark.parametrize("blocks", [(), (SourceBlock(" \n\t"),)])
def test_empty_parsed_documents_do_not_produce_passages(blocks):
    with pytest.raises(DocumentParseError) as exc:
        chunk_document(ParsedDocument("synthetic.txt", "txt", blocks), "doc_test")
    assert exc.value.code == "EMPTY_DOCUMENT"


def test_500_passages_are_allowed_and_501_are_rejected_without_partial_output():
    block = SourceBlock("Synthetic evidence.")
    valid = ParsedDocument("synthetic.txt", "txt", (block,) * 500)
    assert len(chunk_document(valid, "doc_test")) == 500
    with pytest.raises(DocumentParseError, match="500 passages") as exc:
        chunk_document(ParsedDocument("synthetic.txt", "txt", (block,) * 501), "doc_test")
    assert exc.value.code == "BAD_INPUT"


def test_prepared_passage_can_feed_existing_draft_and_verification_tools(metadata):
    from evidencedesk.assistant.tools import draft_answer, verify_answer

    prepared = prepare_document(
        "synthetic.txt", b"Synthetic evidence: use the Reset control.", metadata
    )
    query = QueryInput(
        question="What does the synthetic guide say?",
        context=Scope(product=None, version=None, environment=None),
    )
    retrieval = SearchResult(
        index_revision=0,
        warnings=["Synthetic in-memory test; no index."],
        hits=[
            Hit(
                document=prepared.document,
                passage=prepared.passages[0],
                rank=1,
                bm25_score=None,
                cosine_score=None,
                rrf_score=1.0,
                selection="ranked",
                applicable=True,
            )
        ],
    )
    draft = draft_answer(DraftInput(query=query, retrieval=retrieval)).data
    result = verify_answer(VerifyInput(query=query, retrieval=retrieval, draft=draft))
    assert result.ok and result.data.passed
    support = draft.claims[0].supports[0]
    assert support.passage_id == prepared.passages[0].passage_id
    assert support.quote in prepared.passages[0].text
