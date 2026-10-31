"""Own a tool bundle and serialize backend work within one application process."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from threading import Condition

from evidencedesk.core.factory import Tools


class BackendBusy(RuntimeError):
    """The backend is not accepting work or its single request slot is occupied."""


class BackendRuntime:
    def __init__(self, factory: Callable[[], Tools]):
        self._factory = factory
        self._condition = Condition()
        self._tools: Tools | None = None
        self._ready = False
        self._active = False

    @property
    def ready(self) -> bool:
        with self._condition:
            return self._ready

    def start(self) -> None:
        """Build once per lifespan; failed startup never enables requests."""
        with self._condition:
            if self._tools is not None:
                raise RuntimeError("Backend is already started.")
            tools = self._factory()
            for name in ("ingest", "sources", "search", "draft", "verify"):
                if not callable(getattr(tools, name, None)):
                    raise RuntimeError(f"Backend tool '{name}' is not callable.")
            self._tools = tools
            self._ready = True

    def stop(self) -> None:
        """Reject new work, drain active work, then release the tool bundle."""
        with self._condition:
            self._ready = False
            self._condition.wait_for(lambda: not self._active)
            self._tools = None

    @contextmanager
    def request(self) -> Iterator[Tools]:
        # Hold the slot across the whole query so ingestion cannot change its index
        # between retrieval, drafting, and verification. Health bypasses this slot.
        with self._condition:
            if not self._ready or self._tools is None:
                raise BackendBusy("Backend is not ready to accept requests.")
            if self._active:
                raise BackendBusy("Another backend request is in progress.")
            self._active = True
            tools = self._tools
        try:
            yield tools
        finally:
            with self._condition:
                self._active = False
                self._condition.notify_all()
