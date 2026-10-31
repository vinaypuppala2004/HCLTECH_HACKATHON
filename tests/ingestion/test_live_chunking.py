"""Live grouping retains HTML headings and citation ranges without tiny passages."""

from evidencedesk.ingestion.chunking import LIVE_CHUNKING, prepare_document
from evidencedesk.mocks.fixtures import mock_hit


def test_live_html_sections_group_adjacent_blocks_and_preserve_headings():
    content = (
        b"<h1>Guide</h1>\n<p>First statement.</p>\n<p>Second statement.</p>\n"
        b"<h2>Other</h2>\n<p>Third statement.</p>"
    )
    prepared = prepare_document(
        "guide.html", content, mock_hit().document.metadata, config=LIVE_CHUNKING
    )
    assert len(prepared.chunks) == 2
    first, second = prepared.chunks
    assert first.passage.section_path == ["Guide"]
    assert "First statement." in first.passage.text and "Second statement." in first.passage.text
    assert "Third statement." not in first.passage.text
    assert second.passage.section_path == ["Guide", "Other"]
    assert first.start_line == 1 and first.end_line == 3
    assert second.end_line == 5
    assert (
        prepare_document(
            "renamed.html", content, mock_hit().document.metadata, config=LIVE_CHUNKING
        ).passages
        == prepared.passages
    )
