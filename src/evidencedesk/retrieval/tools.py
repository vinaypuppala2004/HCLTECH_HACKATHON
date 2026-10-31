"""Fixed fixture retrieval. No embedding model or Qdrant is contacted."""

from evidencedesk.contracts.models import Envelope, QueryInput, SearchResult
from evidencedesk.core.responses import success
from evidencedesk.mocks.fixtures import mock_hit


def search_passages(request: QueryInput) -> Envelope[SearchResult]:
    return success(
        SearchResult(
            index_revision=1,
            hits=[mock_hit()],
            warnings=[
                "Mock search ignores question and scope; it always returns the same fixture."
            ],
        )
    )
