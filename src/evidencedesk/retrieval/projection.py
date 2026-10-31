"""Nomic's Matryoshka layer-normalize, prefix, and normalize embedding profile."""

from dataclasses import asdict, dataclass

import numpy as np

from evidencedesk.contracts.models import EmbeddingInput, EmbeddingOutput, Envelope
from evidencedesk.contracts.ports import EmbeddingPort
from evidencedesk.core.responses import failure, success
from evidencedesk.retrieval.embeddings import EMBEDDING_MODEL


@dataclass(frozen=True)
class VectorProfile:
    source_dimensions: int
    dimensions: int
    model: str = EMBEDDING_MODEL
    transform: str = "nomic-mrl-layernorm-prefix-l2-v1"
    prefixes: str = "search-query-document-v1"

    def as_dict(self) -> dict:
        return asdict(self)


class CompactEmbeddings:
    """Keep a trained MRL prefix after layer normalization, then normalize to unit length.

    The layer-norm variance scale cancels in the final L2 normalization. Centering
    all native dimensions before slicing is equivalent and avoids a redundant scale.
    Model inference still computes the native vector; storage and search get smaller.
    """

    def __init__(
        self, native: EmbeddingPort, *, dimensions: int = 512, source_dimensions: int = 768
    ):
        if (
            type(source_dimensions) is not int
            or type(dimensions) is not int
            or not 1 <= dimensions <= source_dimensions
        ):
            raise ValueError("MRL requires integer dimensions: 1 <= target <= source.")
        self._native = native
        self._profile = VectorProfile(source_dimensions, dimensions)

    @property
    def profile(self) -> VectorProfile:
        return self._profile

    def __call__(self, request: EmbeddingInput) -> Envelope[EmbeddingOutput]:
        response = self._native(request)
        if not response.ok or response.data is None:
            return response
        data = response.data
        if (
            data.model != self.profile.model
            or data.dimensions != self.profile.source_dimensions
            or not data.model_digest
        ):
            return failure(
                "INVALID_MODEL_OUTPUT", "Native embeddings do not match the vector profile."
            )
        try:
            values = np.asarray(data.vectors, dtype=np.float64)
            if (
                values.shape != (len(request.texts), self.profile.source_dimensions)
                or not len(request.texts)
                or not np.isfinite(values).all()
            ):
                raise ValueError("Invalid native vectors.")
            centered = values - values.mean(axis=1, keepdims=True)
            reduced = centered[:, : self.profile.dimensions]
            norms = np.linalg.norm(reduced, axis=1, keepdims=True)
            if not np.isfinite(norms).all() or (norms == 0).any():
                raise ValueError("Invalid reduced vectors.")
            vectors = (reduced / norms).tolist()
        except (ValueError, TypeError, OverflowError):
            return failure(
                "INVALID_MODEL_OUTPUT", "Cannot reduce or normalize the embedding vectors."
            )
        return success(
            EmbeddingOutput(
                model=data.model,
                model_digest=data.model_digest,
                dimensions=self.profile.dimensions,
                vectors=vectors,
            )
        )
