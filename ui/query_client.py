"""A3 query requests with explicit, user-readable failures and no mock fallback."""

import httpx

from evidencedesk.contracts.models import Envelope, QueryInput, QueryResult

ERROR_ACTIONS = {
    "BAD_INPUT": "Check your question and context, then submit again.",
    "UNSUPPORTED_FORMAT": "Use a supported PDF, HTML, Markdown, or TXT document.",
    "EMPTY_DOCUMENT": "Use a document containing readable text.",
    "NOT_FOUND": "Refresh the sources and check that the requested document still exists.",
    "INDEX_EMPTY": "No documents are indexed. Add documents through a working ingestion service.",
    "BUSY": "The backend is busy. Wait briefly before submitting again.",
    "EMBEDDING_UNAVAILABLE": "Check Ollama and the configured embedding model before retrying.",
    "MODEL_UNAVAILABLE": "Check Ollama and the configured generation model before retrying.",
    "MODEL_TIMEOUT": "The model took too long. Try the question again when the service is ready.",
    "INVALID_MODEL_OUTPUT": "The model returned an invalid answer. Report repeated failures.",
    "NOT_IMPLEMENTED": "This operation is not implemented in the current backend.",
    "INTERNAL_ERROR": "The backend failed unexpectedly. Check its logs using the request ID.",
}


class QueryServiceError(Exception):
    """A safe display message; raw response bodies and validation inputs stay out of the UI."""


def request_query(backend_url: str, payload: QueryInput) -> QueryResult:
    try:
        response = httpx.post(
            f"{backend_url}/v1/query", json=payload.model_dump(), timeout=30, trust_env=False
        )
    except httpx.TimeoutException:
        raise QueryServiceError(
            "REQUEST_TIMEOUT: The backend did not reply in time. "
            "Check that it is running and submit the question again when ready."
        ) from None
    except (httpx.ConnectError, httpx.InvalidURL):
        raise QueryServiceError(
            "BACKEND_UNREACHABLE: Could not connect to the backend. "
            "Start the FastAPI backend and check BACKEND_URL before retrying."
        ) from None
    except httpx.RequestError:
        raise QueryServiceError(
            "CONNECTION_ERROR: The request could not be completed. "
            "Check the backend connection before submitting again."
        ) from None
    try:
        envelope = Envelope[QueryResult].model_validate(response.json())
    except ValueError:
        status = f"HTTP {response.status_code}: " if not response.is_success else ""
        raise QueryServiceError(
            f"{status}INVALID_RESPONSE: The backend returned an unreadable or invalid reply. "
            "Check the backend service before submitting again."
        ) from None
    if not envelope.ok and envelope.data is None and envelope.error is not None:
        error = envelope.error
        raise QueryServiceError(
            f"{error.code}: {error.message}\n\n{ERROR_ACTIONS[error.code]}\n\n"
            f"Request ID: {envelope.request_id} | Retryable: {'yes' if error.retryable else 'no'}"
        )
    if not response.is_success:
        raise QueryServiceError(
            f"HTTP {response.status_code}: The backend did not return a successful reply. "
            "Check the backend service before submitting again."
        )
    if not envelope.ok or envelope.data is None or envelope.error is not None:
        raise QueryServiceError(
            "INVALID_RESPONSE: The backend returned an inconsistent reply. "
            "Check the backend service before submitting again."
        )
    return envelope.data
