"""One default in-process limiter shared by local generation and embeddings."""

from threading import Lock

MODEL_REQUEST_LOCK = Lock()
