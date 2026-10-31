"""Nomic MRL reduction follows the model card and is stable across calls."""

import numpy as np
import pytest

from evidencedesk.contracts.models import EmbeddingInput, EmbeddingOutput
from evidencedesk.core.responses import failure, success
from evidencedesk.retrieval.embeddings import EMBEDDING_MODEL
from evidencedesk.retrieval.projection import CompactEmbeddings


def test_mrl_matches_layer_normalize_then_prefix_then_l2():
    values = np.array([[2.0, -1, 4, 3], [3.0, 4, -2, 6]])

    def native(request):
        return success(
            EmbeddingOutput(
                model=EMBEDDING_MODEL, model_digest="digest", dimensions=4, vectors=values.tolist()
            )
        )

    embed = CompactEmbeddings(native, source_dimensions=4, dimensions=2)
    result = embed(EmbeddingInput(texts=["one", "two"], kind="document")).data
    assert result is not None
    normalized = (values - values.mean(axis=1, keepdims=True)) / np.sqrt(
        values.var(axis=1, keepdims=True) + 1e-5
    )
    expected = normalized[:, :2]
    expected /= np.linalg.norm(expected, axis=1, keepdims=True)
    np.testing.assert_allclose(result.vectors, expected)
    np.testing.assert_allclose(np.linalg.norm(result.vectors, axis=1), [1, 1])
    assert result.dimensions == 2 and result.model_digest == "digest"
    repeated = embed(EmbeddingInput(texts=["one", "two"], kind="query")).data
    assert repeated.vectors == result.vectors


@pytest.mark.parametrize("dimensions", [0, -1, 769, True, "512"])
def test_invalid_dimension_selection_is_explicit(dimensions):
    with pytest.raises(ValueError, match="dimensions"):
        CompactEmbeddings(lambda _: None, dimensions=dimensions)


def test_embedding_failure_is_preserved():
    error = failure("MODEL_TIMEOUT", "Test timeout.", retryable=True)
    result = CompactEmbeddings(lambda _: error)(EmbeddingInput(texts=["one"], kind="query"))
    assert result is error


@pytest.mark.parametrize("vectors", [[[1, 1, 1, 1]], [[1, 2, 3]], []])
def test_invalid_or_constant_native_vectors_fail(vectors):
    def native(request):
        return success(
            EmbeddingOutput(
                model=EMBEDDING_MODEL, model_digest="digest", dimensions=4, vectors=vectors
            )
        )

    result = CompactEmbeddings(native, source_dimensions=4, dimensions=2)(
        EmbeddingInput(texts=["one"], kind="query")
    )
    assert not result.ok and result.error.code == "INVALID_MODEL_OUTPUT"


def test_wrong_native_model_is_never_relabelled():
    def native(request):
        return success(
            EmbeddingOutput(
                model="qwen3:4b", model_digest="digest", dimensions=4, vectors=[[1, 2, 3, 4]]
            )
        )

    result = CompactEmbeddings(native, source_dimensions=4, dimensions=2)(
        EmbeddingInput(texts=["one"], kind="query")
    )
    assert not result.ok and result.error.code == "INVALID_MODEL_OUTPUT"
