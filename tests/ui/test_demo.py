"""A5 presentation stays synthetic, contract-valid, and independent of services."""

from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import httpx
import pytest
from streamlit.testing.v1 import AppTest

from evidencedesk.contracts.models import QueryResult
from ui.demo_examples import demo_examples

DEMO_PATH = Path(__file__).resolve().parents[2] / "ui" / "demo.py"
EXAMPLE_TITLES = [example.title for example in demo_examples()]


@pytest.fixture
def preview(monkeypatch):
    def no_network(*args, **kwargs):
        pytest.fail("The synthetic presentation must not call any backend or external service.")

    monkeypatch.setattr(httpx, "post", no_network)
    monkeypatch.setattr(httpx, "get", no_network)
    return AppTest.from_file(DEMO_PATH, default_timeout=15)


@pytest.mark.parametrize("index", range(7))
def test_presentation_data_has_real_excerpt_matches_and_no_live_claims(index):
    example = demo_examples()[index]
    result = QueryResult.model_validate(example.result.model_dump())
    assert result.mode == "mock"
    assert result.trace == [], "No invented model or retrieval timings."
    assert result.retrieval.index_revision == 0
    hits = {hit.passage.passage_id: hit for hit in result.retrieval.hits}
    for hit in hits.values():
        assert hit.document.metadata.origin == "synthetic"
        assert hit.document.metadata.source_url is None
        assert hit.passage.document_id == hit.document.document_id
        assert hit.document.sha256 == sha256(hit.passage.text.encode()).hexdigest()
        assert hit.passage.page is None
    for claim in result.result.claims:
        assert any(hits[support.passage_id].applicable for support in claim.supports)
        for support in claim.supports:
            assert support.quote and support.quote in hits[support.passage_id].passage.text
    for conflict in result.result.conflicts:
        for side in conflict.sides:
            assert side.quote and side.quote in hits[side.passage_id].passage.text
        if conflict.resolution == "unresolved":
            assert not conflict.selected_passage_ids
        else:
            assert conflict.selected_passage_ids
            assert all(hits[identifier].applicable for identifier in conflict.selected_passage_ids)
    if result.result.status in {"needs_context", "not_found", "insufficient_evidence"}:
        assert not result.result.claims


@pytest.mark.parametrize("title", EXAMPLE_TITLES)
def test_every_example_renders_without_services_and_keeps_preview_labels(preview, title):
    preview.run()
    preview.selectbox(key="presentation_example").select(title).run()
    assert not preview.exception
    assert any("SYNTHETIC PRESENTATION PREVIEW" in warning.value for warning in preview.warning)
    assert any(
        "not a live query or a saved live result" in warning.value for warning in preview.warning
    )
    assert any(
        "No API, model, or index calls. No evaluation scores." in c.value for c in preview.caption
    )
    assert not preview.chat_input
    assert not preview.metric
    assert any(expander.label == "Presenter notes" for expander in preview.expander)
    assert any("remain unimplemented" in text.value for text in preview.markdown)
    preview.run()
    assert not preview.exception


def test_preview_scope_action_does_not_resolve_or_replace_a_fixed_example(preview):
    preview.run()
    preview.selectbox(key="presentation_example").select("2. Compare versions").run()
    assert any("Unresolved conflict" in warning.value for warning in preview.warning)
    preview.button(key="presentation_1_conflict_0_side_1").click().run()
    assert not preview.exception
    assert preview.text_input(key="scope_version").value == "v2"
    assert any("Unresolved conflict" in warning.value for warning in preview.warning)
    assert not any("Selected by backend" in c.value for c in preview.caption)
    preview.selectbox(key="presentation_example").select("3. Context selects v2").run()
    assert not preview.exception
    assert preview.text_input(key="scope_version").value == "v2"
    assert any("Resolved by context" in info.value for info in preview.info)
    assert any("Selected by backend" in c.value for c in preview.caption)
    assert any("API applicability: not applicable" == c.value for c in preview.caption)


def test_presentation_does_not_change_chat_history(preview):
    saved = [{"role": "user", "text": "An existing main-app turn."}]
    preview.session_state.messages = deepcopy(saved)
    preview.run()
    preview.selectbox(key="presentation_example").select("7. Failed verification").run()
    assert not preview.exception
    assert preview.session_state.messages == saved
    assert any("not enough verified evidence" in warning.value for warning in preview.warning)
    assert not any(
        expander.label.startswith("Citations for claim") for expander in preview.expander
    )


def test_examples_are_independent_between_runs():
    first = demo_examples()
    first[0].result.result.claims[0].text = "Changed during a presentation session"
    assert (
        demo_examples()[0].result.result.claims[0].text
        == "Password reset links expire after 15 minutes."
    )
