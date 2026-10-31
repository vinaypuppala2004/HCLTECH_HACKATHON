"""D3 dataset integrity checks; no retriever, model provider, or metric execution."""

import json
import shutil
from collections import Counter

import pytest

from evaluation.dataset import (
    CATEGORY_COUNTS,
    DATA_ROOT,
    content_hash,
    load_cases,
    read_json,
    validate_dataset,
)

# Independent anchor: resealing held-out labels must require deliberate review.
FROZEN_MANIFEST_SHA256 = "dc74cdf0118b45eb92dc8fef48bb507b7735c05c17c0110f591fbd044009b190"


@pytest.fixture
def dataset_copy(tmp_path):
    target = tmp_path / "synthetic-v1"
    shutil.copytree(DATA_ROOT, target)
    return target


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def test_dataset_has_24_grounded_labels_and_the_required_category_mix():
    assert validate_dataset() == {"development": 16, "heldout": 8}
    development, heldout = load_cases(), load_cases("heldout")
    assert Counter(case.category for case in development + heldout) == CATEGORY_COUNTS
    assert Counter(case.category for case in heldout) == {
        "direct": 2,
        "paraphrase": 2,
        "conflict_version": 2,
        "ambiguous": 1,
        "unsupported": 1,
    }
    assert {case.family_id for case in development}.isdisjoint({case.family_id for case in heldout})


def test_frozen_manifest_has_an_independent_content_anchor():
    assert content_hash(read_json(DATA_ROOT / "freeze.json")) == FROZEN_MANIFEST_SHA256


def test_default_loader_does_not_read_heldout_labels(dataset_copy):
    (dataset_copy / "heldout.json").unlink()
    (dataset_copy / "freeze.json").unlink()
    assert len(load_cases(root=dataset_copy)) == 16


@pytest.mark.parametrize("split", ["all", "../heldout", ""])
def test_split_must_be_explicit_and_valid(split):
    with pytest.raises(ValueError, match="Select development or heldout explicitly"):
        load_cases(split)


@pytest.mark.parametrize("filename", ["heldout.json", "sources.json"])
def test_frozen_label_or_source_changes_fail_validation(dataset_copy, filename):
    path = dataset_copy / filename
    value = read_json(path)
    if filename == "heldout.json":
        value[0]["query"]["question"] = "A different held-out question"
    else:
        value["passages"][0]["text"] += " Changed source text."
    write_json(path, value)
    with pytest.raises(ValueError, match=f"Frozen content changed: {filename}"):
        validate_dataset(dataset_copy)
    with pytest.raises(ValueError, match="Frozen content changed"):
        load_cases("heldout", dataset_copy)


def test_freeze_hash_ignores_json_formatting_and_checkout_line_endings(dataset_copy):
    for filename in ("heldout.json", "sources.json"):
        path = dataset_copy / filename
        text = json.dumps(read_json(path), indent=4, sort_keys=True) + "\n"
        path.write_bytes(text.replace("\n", "\r\n").encode())
    assert validate_dataset(dataset_copy) == {"development": 16, "heldout": 8}


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ("count", "Expected 16 development and 8 held-out cases"),
        ("duplicate_id", "Case IDs must be unique"),
        ("duplicate_question", "Duplicate questions"),
        ("categories", "Category counts differ"),
        ("family_leak", "Question families leak across splits"),
        ("unknown_passage", "unknown relevant passage"),
        ("false_quote", "quote must be an exact nonempty excerpt"),
        ("wrong_scope", "claim needs applicable evidence"),
        ("extra_evidence", "relevant passages must match labelled evidence"),
        ("bad_options", "clarification options must match relevant source metadata"),
        ("scope_already_supplied", "scope already supplied"),
        ("wrong_version_selection", "selected conflict evidence is outside scope"),
        ("unresolved_selection", "unresolved conflict selects no side"),
        ("unsupported_claim", "fallback/clarification must not assert facts"),
    ],
)
def test_invalid_labels_and_split_leakage_are_rejected(dataset_copy, change, message):
    path = dataset_copy / "development.json"
    cases = read_json(path)
    if change == "count":
        cases.pop()
    elif change == "duplicate_id":
        cases[1]["case_id"] = cases[0]["case_id"]
    elif change == "duplicate_question":
        cases[1]["query"]["question"] = cases[0]["query"]["question"]
    elif change == "categories":
        cases[0]["category"] = "paraphrase"
    elif change == "family_leak":
        cases[0]["family_id"] = "service_token_rotation"
    elif change == "unknown_passage":
        cases[0]["relevant_passage_ids"] = ["missing_passage"]
    elif change == "false_quote":
        cases[0]["expected"]["claims"][0]["supports"][0]["quote"] = "An invented quotation."
    elif change == "wrong_scope":
        cases[0]["query"]["context"]["version"] = "2.0"
    elif change == "extra_evidence":
        cases[0]["relevant_passage_ids"].append("eval_logs_v1")
    elif change == "bad_options":
        cases[12]["expected"]["clarification"]["options"] = ["1.0", "3.0"]
    elif change == "scope_already_supplied":
        cases[12]["query"]["context"]["version"] = "1.0"
    elif change == "wrong_version_selection":
        cases[10]["expected"]["conflicts"][0]["selected_passage_ids"] = ["eval_retention_v1"]
    elif change == "unresolved_selection":
        cases[11]["expected"]["conflicts"][0]["selected_passage_ids"] = ["eval_maintenance_policy"]
    elif change == "unsupported_claim":
        cases[14]["expected"]["claims"] = cases[0]["expected"]["claims"]
    write_json(path, cases)
    with pytest.raises(ValueError, match=message):
        validate_dataset(dataset_copy)


def test_unsupported_cases_have_no_fabricated_citations():
    cases = load_cases() + load_cases("heldout")
    unsupported = [case for case in cases if case.category == "unsupported"]
    assert len(unsupported) == 3
    for case in unsupported:
        assert case.expected.status == "not_found"
        assert case.expected.fallback_reason == "no_support"
        assert case.expected.claims == []
        assert case.expected.conflicts == []
        assert case.relevant_passage_ids == []
