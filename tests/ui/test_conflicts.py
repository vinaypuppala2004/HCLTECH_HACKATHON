"""A2 scope controls and side-by-side conflict behavior against contract fixtures."""

from pathlib import Path

import httpx
import pytest
from streamlit.testing.v1 import AppTest

from evidencedesk.contracts.models import (
    Conflict,
    Draft,
    QueryResult,
    SearchResult,
    Support,
    Verification,
)
from evidencedesk.mocks.fixtures import mock_hit

UI_PATH = Path(__file__).resolve().parents[2] / "ui" / "app.py"
BACKEND_URL = "http://127.0.0.1:8000"


def conflict_result(*, resolution="unresolved", kind="version_difference", side_count=2):
    hits = []
    for index in range(1, side_count + 1):
        hit = mock_hit().model_copy(deep=True)
        hit.document.document_id = f"doc_v{index}"
        hit.document.filename = f"synthetic-v{index}.pdf"
        hit.document.format = "pdf"
        hit.document.metadata.title = f"Synthetic guide v{index}"
        hit.document.metadata.product = "EvidenceDesk"
        hit.document.metadata.version = f"v{index}"
        hit.document.metadata.environment = "production" if index == 1 else "staging"
        hit.passage.passage_id = f"passage_v{index}"
        hit.passage.document_id = hit.document.document_id
        hit.passage.page = index
        hit.passage.text = f"Context before. Follow procedure {index}. Context after."
        hit.rank = index
        hit.selection = "ranked" if index == 1 else "version_counterpart"
        hit.applicable = index == 1
        hits.append(hit)
    return QueryResult(
        mode="mock",
        result=Draft(
            status="conflict",
            claims=[],
            conflicts=[
                Conflict(
                    conflict_id="synthetic_conflict",
                    kind=kind,
                    topic="Synthetic procedure difference",
                    sides=[
                        Support(passage_id=hit.passage.passage_id, quote=f"Follow procedure {i}.")
                        for i, hit in enumerate(hits, start=1)
                    ],
                    resolution=resolution,
                    selected_passage_ids=["passage_v2"]
                    if resolution == "resolved_by_context"
                    else [],
                )
            ],
            clarification=None,
            fallback_reason=None,
        ),
        retrieval=SearchResult(index_revision=1, hits=hits, warnings=[]),
        verification=Verification(passed=False, evidence_strength="limited", checks=[]),
        trace=[],
    )


@pytest.fixture
def frontend(monkeypatch):
    monkeypatch.setenv("APP_MODE", "mock")
    monkeypatch.setenv("BACKEND_URL", BACKEND_URL)
    calls = []
    result = conflict_result()

    def route_to_backend(url, *, json, **kwargs):
        assert url == f"{BACKEND_URL}/v1/query"
        calls.append(json)
        return httpx.Response(
            200,
            json={
                "ok": True,
                "request_id": "req_synthetic_conflict",
                "data": result.model_dump(),
                "error": None,
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", route_to_backend)
    yield AppTest.from_file(UI_PATH, default_timeout=15), calls, result


def submit(ui):
    ui.chat_input[0].set_value("Which procedure should I follow?").run()
    assert not ui.exception


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        (("", "", ""), {"product": None, "version": None, "environment": None}),
        (("  ", "\t", "  "), {"product": None, "version": None, "environment": None}),
        (
            (" EvidenceDesk ", " v2-RC1 ", " Production "),
            {"product": "EvidenceDesk", "version": "v2-RC1", "environment": "Production"},
        ),
        (("", " v2 ", ""), {"product": None, "version": "v2", "environment": None}),
    ],
)
def test_context_controls_send_explicit_scope_without_requests_on_edit(frontend, values, expected):
    ui, calls, _ = frontend
    ui.run()
    for field, value in zip(["product", "version", "environment"], values):
        ui.text_input(key=f"scope_{field}").set_value(value).run()
    assert not calls
    submit(ui)
    assert calls == [
        {"question": "Which procedure should I follow?", "context": expected},
    ]


@pytest.mark.parametrize("mode", ["mock", "live"])
@pytest.mark.parametrize("kind", ["contradiction", "version_difference"])
def test_conflict_sides_show_exact_quotes_and_source_context(frontend, mode, kind):
    ui, _, result = frontend
    result.mode = mode
    result.result.conflicts[0].kind = kind
    ui.run()
    submit(ui)
    columns = ui.chat_message[1].columns
    assert len(columns) == 2
    for index, column in enumerate(columns, start=1):
        assert f"Follow procedure {index}." in [element.value for element in column.text]
        assert f"Synthetic guide v{index}" in [element.value for element in column.text]
        captions = [element.value for element in column.caption]
        assert any(f"Source: doc_v{index}" in value for value in captions)
        assert f"Passage: passage_v{index}" in captions
        assert f"Page: {index}" in captions
        assert any(f"Product: EvidenceDesk | Version: v{index}" in value for value in captions)
        assert "Synthetic fixture — mock evidence" in captions
    assert any(f"Kind: {kind}" in caption.value for caption in ui.caption)
    assert any(f"Mode: {mode}" in caption.value for caption in ui.caption)
    assert "API applicability: applicable" in [caption.value for caption in columns[0].caption]
    assert "API applicability: not applicable" in [caption.value for caption in columns[1].caption]
    assert any("Unresolved conflict" in warning.value for warning in ui.warning)
    assert not any("Selected by backend" in caption.value for caption in ui.caption)


def test_resolved_conflict_marks_only_backend_selected_side(frontend):
    ui, _, result = frontend
    result.result.conflicts[0].resolution = "resolved_by_context"
    result.result.conflicts[0].selected_passage_ids = ["passage_v2"]
    ui.run()
    submit(ui)
    columns = ui.chat_message[1].columns
    assert not any("Selected by backend" in caption.value for caption in columns[0].caption)
    assert any("Selected by backend" in caption.value for caption in columns[1].caption)
    assert any("Resolved by context" in info.value for info in ui.info)
    assert not any("Unresolved conflict" in warning.value for warning in ui.warning)


def test_use_context_applies_to_next_query_without_locally_resolving(frontend):
    ui, calls, _ = frontend
    ui.run()
    submit(ui)
    ui.button(key="reply_1_conflict_0_side_1").click().run()
    assert not ui.exception
    assert ui.text_input(key="scope_product").value == "EvidenceDesk"
    assert ui.text_input(key="scope_version").value == "v2"
    assert ui.text_input(key="scope_environment").value == "staging"
    assert len(calls) == 1
    assert any("Unresolved conflict" in warning.value for warning in ui.warning)
    assert not any("Selected by backend" in caption.value for caption in ui.caption)
    submit(ui)
    assert calls[1]["context"] == {
        "product": "EvidenceDesk",
        "version": "v2",
        "environment": "staging",
    }
    assert not ui.exception, "Conflict controls need unique keys across replies."
    ui.run()
    assert len(calls) == 2


def test_missing_side_metadata_keeps_quote_visible_without_context_action(frontend):
    ui, _, result = frontend
    result.retrieval.hits = result.retrieval.hits[:1]
    ui.run()
    submit(ui)
    second = ui.chat_message[1].columns[1]
    assert "Follow procedure 2." in [element.value for element in second.text]
    assert "Passage: passage_v2" in [element.value for element in second.caption]
    assert any("metadata is unavailable" in warning.value for warning in second.warning)
    assert not second.button


def test_null_source_context_clears_controls_instead_of_reusing_old_values(frontend):
    ui, _, result = frontend
    metadata = result.retrieval.hits[1].document.metadata
    metadata.product = metadata.version = metadata.environment = None
    ui.run()
    for field in ["product", "version", "environment"]:
        ui.text_input(key=f"scope_{field}").set_value("Old value").run()
    submit(ui)
    ui.button(key="reply_1_conflict_0_side_1").click().run()
    assert not ui.exception
    for field in ["product", "version", "environment"]:
        assert ui.text_input(key=f"scope_{field}").value == ""


def test_multiple_conflicts_and_more_than_two_sides_are_all_visible(frontend):
    ui, _, result = frontend
    three_sides = conflict_result(side_count=3)
    result.retrieval = three_sides.retrieval
    result.result.conflicts = [three_sides.result.conflicts[0]]
    result.result.conflicts.append(
        result.result.conflicts[0].model_copy(update={"conflict_id": "another_conflict"})
    )
    ui.run()
    submit(ui)
    assert len(ui.chat_message[1].columns) == 8
    for index in range(1, 4):
        assert [element.value for element in ui.text].count(f"Follow procedure {index}.") == 2
    assert len([button for button in ui.button if button.label == "Use this context"]) == 6


def test_no_conflicts_does_not_invent_a_comparison(frontend):
    ui, _, result = frontend
    result.result.conflicts = []
    ui.run()
    submit(ui)
    assert not any(heading.value == "Conflicting evidence" for heading in ui.subheader)
    assert not [button for button in ui.button if button.label == "Use this context"]
