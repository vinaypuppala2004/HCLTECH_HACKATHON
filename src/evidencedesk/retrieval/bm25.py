"""Dependency-free BM25 over committed passage text and visible source headings."""

import math
import re
import unicodedata
from collections import Counter
from collections.abc import Mapping, Set


def tokenize(text: str) -> list[str]:
    """Normalize case/Unicode and split identifiers, paths, and words into terms."""
    return re.findall(r"[^\W_]+", unicodedata.normalize("NFKC", text).casefold())


class BM25Corpus:
    """Cache token counts; calculate corpus statistics inside the requested scope."""

    def __init__(self, passages: Mapping[str, str], *, k1: float = 1.5, b: float = 0.75):
        if not math.isfinite(k1) or k1 <= 0 or not math.isfinite(b) or not 0 <= b <= 1:
            raise ValueError("BM25 requires k1 > 0 and 0 <= b <= 1.")
        self._k1 = k1
        self._b = b
        self._counts = {
            passage_id: Counter(tokenize(text)) for passage_id, text in passages.items()
        }
        self._lengths = {
            passage_id: sum(counts.values()) for passage_id, counts in self._counts.items()
        }

    def scores(self, question: str, passage_ids: Set[str] | None = None) -> dict[str, float]:
        eligible = sorted(
            self._counts if passage_ids is None else self._counts.keys() & passage_ids
        )
        scores = {passage_id: 0.0 for passage_id in eligible}
        terms = sorted(set(tokenize(question)))
        if not eligible or not terms:
            return scores
        average_length = sum(self._lengths[passage_id] for passage_id in eligible) / len(eligible)
        if average_length == 0:
            return scores
        frequencies = {
            term: sum(term in self._counts[passage_id] for passage_id in eligible) for term in terms
        }
        for passage_id in eligible:
            counts = self._counts[passage_id]
            normalization = self._k1 * (
                1 - self._b + self._b * self._lengths[passage_id] / average_length
            )
            for term in terms:
                frequency = counts.get(term, 0)
                if frequency == 0:
                    continue
                document_frequency = frequencies[term]
                inverse_document_frequency = math.log1p(
                    (len(eligible) - document_frequency + 0.5) / (document_frequency + 0.5)
                )
                scores[passage_id] += inverse_document_frequency * (
                    frequency * (self._k1 + 1) / (frequency + normalization)
                )
        return scores


def reciprocal_rank_fusion(
    lexical_scores: Mapping[str, float],
    semantic_scores: Mapping[str, float],
    *,
    k: int = 60,
) -> list[tuple[str, float]]:
    """Fuse ranked channels, excluding zero-match BM25 entries from its channel."""
    if type(k) is not int or k < 1:
        raise ValueError("RRF k must be a positive integer.")
    if any(not math.isfinite(score) for score in lexical_scores.values()) or any(
        not math.isfinite(score) for score in semantic_scores.values()
    ):
        raise ValueError("Ranking scores must be finite.")
    lexical = sorted(
        (passage_id for passage_id, score in lexical_scores.items() if score > 0),
        key=lambda passage_id: (-lexical_scores[passage_id], passage_id),
    )
    semantic = sorted(
        semantic_scores, key=lambda passage_id: (-semantic_scores[passage_id], passage_id)
    )
    fused: dict[str, float] = {}
    for channel in (lexical, semantic):
        for rank, passage_id in enumerate(channel, start=1):
            fused[passage_id] = fused.get(passage_id, 0.0) + 1.0 / (k + rank)
    return sorted(fused.items(), key=lambda item: (-item[1], item[0]))
