"""Synthetic, offline parser checks; these fixtures are not curated public sources."""

import codecs
from io import BytesIO

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from evidencedesk.ingestion.parsers import (
    MAX_FILE_BYTES,
    DocumentParseError,
    parse_document,
)


def make_pdf(pages: list[str | None], *, encrypted: bool = False) -> bytes:
    """Create a real text-layer PDF in memory without a second PDF dependency."""
    writer = PdfWriter()
    for text in pages:
        page = writer.add_blank_page(width=612, height=792)
        if text is None:
            continue
        page[NameObject("/Resources")] = DictionaryObject(
            {
                NameObject("/Font"): DictionaryObject(
                    {
                        NameObject("/F1"): DictionaryObject(
                            {
                                NameObject("/Type"): NameObject("/Font"),
                                NameObject("/Subtype"): NameObject("/Type1"),
                                NameObject("/BaseFont"): NameObject("/Helvetica"),
                            }
                        )
                    }
                )
            }
        )
        stream = DecodedStreamObject()
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream.set_data(f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode("ascii"))
        page[NameObject("/Contents")] = stream
    if encrypted:
        writer.encrypt("synthetic-test-password")
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


@pytest.mark.parametrize(
    ("filename", "document_format", "content"),
    [
        ("guide.txt", "txt", b"Synthetic guide"),
        ("GUIDE.TXT", "txt", b"Synthetic guide"),
        ("guide.md", "markdown", b"# Synthetic guide"),
        ("guide.markdown", "markdown", b"# Synthetic guide"),
        ("guide.html", "html", b"<p>Synthetic guide</p>"),
        ("guide.htm", "html", b"<p>Synthetic guide</p>"),
        ("folder\\GUIDE.MD", "markdown", b"# Synthetic guide"),
        ("guide.PDF", "pdf", make_pdf(["Synthetic guide"])),
    ],
)
def test_supported_extensions(filename, document_format, content):
    result = parse_document(filename, content)
    assert result.filename == filename
    assert result.format == document_format
    assert "Synthetic guide" in result.blocks[0].text
    if document_format != "pdf":
        assert all(block.page is None for block in result.blocks)


@pytest.mark.parametrize(
    "content",
    [
        "Synthetic café\r\n  keep spaces\rLast line".encode("utf-8"),
        codecs.BOM_UTF8 + "Synthetic café\r\n  keep spaces\rLast line".encode("utf-8"),
        "Synthetic café\r\n  keep spaces\rLast line".encode("utf-16"),
        codecs.BOM_UTF16_BE + "Synthetic café\r\n  keep spaces\rLast line".encode("utf-16-be"),
    ],
)
def test_text_preserves_spelling_whitespace_and_locations(content):
    block = parse_document("synthetic.txt", content).blocks[0]
    assert block.text == "Synthetic café\n  keep spaces\nLast line"
    assert (block.start_line, block.end_line) == (1, 3)
    assert block.section_path == ()
    assert block.page is None


@pytest.mark.parametrize("filename", ["synthetic.txt", "synthetic.md"])
def test_unicode_separators_do_not_shift_source_line_locations(filename):
    source = "Synthetic\u2028separator\ftext\n# Heading\nEvidence.\n"
    blocks = parse_document(filename, source.encode()).blocks
    assert "".join(block.text for block in blocks) == source
    if filename.endswith(".txt"):
        assert [(block.start_line, block.end_line) for block in blocks] == [(1, 3)]
    else:
        assert [(block.start_line, block.end_line) for block in blocks] == [(1, 1), (2, 3)]
        assert blocks[1].section_path == ("Heading",)
        assert blocks[1].text == "# Heading\nEvidence.\n"


def test_markdown_preserves_source_ranges_and_heading_ancestry():
    source = (
        "Synthetic introduction.\n\n"
        "# **Guide**\n\n"
        "Keep *exact* source spelling.\n\n"
        "### Reset `password`\n"
        "Use the **Reset** control.\n\n"
        "## Access\n"
        "Contact support.\n\n"
        "# Other\n"
        "A new topic.\n"
    )
    result = parse_document("synthetic.md", source.encode())
    assert [block.section_path for block in result.blocks] == [
        (),
        ("Guide",),
        ("Guide", "Reset password"),
        ("Guide", "Access"),
        ("Other",),
    ]
    assert [(block.start_line, block.end_line) for block in result.blocks] == [
        (1, 2),
        (3, 6),
        (7, 9),
        (10, 12),
        (13, 14),
    ]
    assert "".join(block.text for block in result.blocks) == source
    for block in result.blocks:
        lines = source.splitlines(keepends=True)
        assert block.text == "".join(lines[block.start_line - 1 : block.end_line])


def test_markdown_setext_headings_and_code_are_not_confused():
    source = (
        "Synthetic guide\n===============\n\n"
        "```markdown\n# Not a heading\n```\n\n"
        "    # Also code\n\n"
        "Reset\n-----\n\n"
        "- Step one\n- Step two\n"
    )
    blocks = parse_document("synthetic.md", source.encode()).blocks
    assert [block.section_path for block in blocks] == [
        ("Synthetic guide",),
        ("Synthetic guide", "Reset"),
    ]
    assert "# Not a heading" in blocks[0].text
    assert "    # Also code" in blocks[0].text
    assert "- Step one\n- Step two" in blocks[1].text
    assert "".join(block.text for block in blocks) == source


def test_markdown_long_sections_remain_unchunked():
    source = "# Synthetic guide\n\n" + "Some evidence. " * 2000
    blocks = parse_document("synthetic.md", source.encode()).blocks
    assert len(blocks) == 1
    assert blocks[0].text == source


def test_html_retains_headings_visible_text_entities_and_line_ranges():
    source = (
        "<h1>Synthetic Guide</h1>\n"
        "<p>Reset <em>your</em> pass<strong>word</strong> &amp; sign in.</p>\n"
        "<h3>Local <code>setup</code></h3>\n"
        "<p>Keep the old version.</p>\n"
        "<h2>Access</h2>\n"
        "<p>Ask support.</p>"
    )
    blocks = parse_document("synthetic.html", source.encode()).blocks
    assert [block.text for block in blocks] == [
        "Synthetic Guide",
        "Reset your password & sign in.",
        "Local setup",
        "Keep the old version.",
        "Access",
        "Ask support.",
    ]
    assert [block.section_path for block in blocks] == [
        ("Synthetic Guide",),
        ("Synthetic Guide",),
        ("Synthetic Guide", "Local setup"),
        ("Synthetic Guide", "Local setup"),
        ("Synthetic Guide", "Access"),
        ("Synthetic Guide", "Access"),
    ]
    assert [(block.start_line, block.end_line) for block in blocks] == [
        (line, line) for line in range(1, 7)
    ]
    assert all(block.page is None for block in blocks)


def test_html_excludes_noncontent_and_hidden_subtrees():
    source = b"""<!doctype html><html><head><title>Hidden title</title>
    <style>.x {color:red}</style></head><body><h1>Synthetic guide</h1>
    <script>not evidence</script><template><p>hidden template</p></template>
    <noscript>hidden fallback</noscript><!-- hidden comment -->
    <div hidden><span>hidden text</span><br><input></div>
    <p aria-hidden="true">hidden accessible text</p>
    <p>Visible <span hidden>hidden inline</span>evidence.</p></body></html>"""
    blocks = parse_document("synthetic.html", source).blocks
    assert [block.text for block in blocks] == ["Synthetic guide", "Visible evidence."]


def test_html_preformatted_code_and_unclosed_paragraph():
    source = b"<h1>Synthetic</h1><pre>line one\n    indented line two</pre><p>Last paragraph"
    blocks = parse_document("synthetic.html", source).blocks
    assert [block.text for block in blocks] == [
        "Synthetic",
        "line one\n    indented line two",
        "Last paragraph",
    ]


def test_pdf_preserves_original_page_numbers_after_blank_page():
    result = parse_document(
        "synthetic.pdf", make_pdf(["First (exact) quote.", None, "Third page."])
    )
    assert [block.page for block in result.blocks] == [1, 3]
    assert [block.text for block in result.blocks] == ["First (exact) quote.", "Third page."]
    assert all(block.section_path == () for block in result.blocks)
    assert all(block.start_line is None and block.end_line is None for block in result.blocks)
    assert result.warnings == ("Page 2 has no extractable text; OCR is not supported.",)


@pytest.mark.parametrize("filename", ["guide.docx", "guide", "guide.pdf.exe"])
def test_unsupported_formats_are_explicit(filename):
    with pytest.raises(DocumentParseError) as exc:
        parse_document(filename, b"Synthetic text")
    assert exc.value.code == "UNSUPPORTED_FORMAT"


@pytest.mark.parametrize(
    ("filename", "content"),
    [
        ("synthetic.txt", b""),
        ("synthetic.txt", b" \r\n\t"),
        ("synthetic.txt", codecs.BOM_UTF8),
        ("synthetic.md", b"\n\n"),
        ("synthetic.html", b"<html><body><!-- comment --><p> </p></body></html>"),
        ("synthetic.html", b"<script>not evidence</script>"),
        ("synthetic.pdf", make_pdf([None])),
        ("synthetic.pdf", make_pdf([])),
    ],
)
def test_empty_documents_fail_without_success_output(filename, content):
    with pytest.raises(DocumentParseError) as exc:
        parse_document(filename, content)
    assert exc.value.code == "EMPTY_DOCUMENT"


@pytest.mark.parametrize("filename", ["synthetic.txt", "synthetic.md", "synthetic.html"])
@pytest.mark.parametrize("content", [b"invalid \xff", b"NUL \x00 text", codecs.BOM_UTF16_LE + b"x"])
def test_invalid_text_is_never_silently_replaced(filename, content):
    with pytest.raises(DocumentParseError) as exc:
        parse_document(filename, content)
    assert exc.value.code == "BAD_INPUT"


@pytest.mark.parametrize(
    "content", [b"not a PDF", make_pdf(["Text"])[:150], make_pdf(["Text"], encrypted=True)]
)
def test_corrupt_and_encrypted_pdfs_fail(content):
    with pytest.raises(DocumentParseError) as exc:
        parse_document("synthetic.pdf", content)
    assert exc.value.code == "BAD_INPUT"


def test_pdf_does_not_return_partial_pages_on_extraction_failure(monkeypatch):
    from pypdf import PageObject

    original = PageObject.extract_text

    def fail_second_page(page, **kwargs):
        text = original(page, **kwargs)
        if text == "Bad page":
            raise ValueError("Synthetic damaged font")
        return text

    monkeypatch.setattr(PageObject, "extract_text", fail_second_page)
    with pytest.raises(DocumentParseError, match="corrupt data") as exc:
        parse_document("synthetic.pdf", make_pdf(["Good page", "Bad page"]))
    assert exc.value.code == "BAD_INPUT"


def test_file_size_limit():
    with pytest.raises(DocumentParseError, match="10 MB") as exc:
        parse_document("synthetic.txt", b"x" * (MAX_FILE_BYTES + 1))
    assert exc.value.code == "BAD_INPUT"


def test_pdf_page_limit():
    with pytest.raises(DocumentParseError, match="100-page") as exc:
        parse_document("synthetic.pdf", make_pdf(["Synthetic"] * 101))
    assert exc.value.code == "BAD_INPUT"


def test_pdf_accepts_exactly_100_pages():
    result = parse_document("synthetic.pdf", make_pdf(["Synthetic"] * 100))
    assert len(result.blocks) == 100
    assert result.blocks[-1].page == 100
