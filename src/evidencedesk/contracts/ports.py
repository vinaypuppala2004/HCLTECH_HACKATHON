"""Dependency ports: owners can implement modules against these signatures."""

from typing import Protocol

from evidencedesk.contracts.models import (
    Draft,
    DraftInput,
    EmbeddingInput,
    EmbeddingOutput,
    Envelope,
    GenerationInput,
    GenerationOutput,
    IngestInput,
    IngestResult,
    QueryInput,
    SearchResult,
    SourcesInput,
    SourcesResult,
    Verification,
    VerifyInput,
)


class IngestTool(Protocol):
    def __call__(self, request: IngestInput) -> Envelope[IngestResult]: ...


class SourcesTool(Protocol):
    def __call__(self, request: SourcesInput) -> Envelope[SourcesResult]: ...


class SearchTool(Protocol):
    def __call__(self, request: QueryInput) -> Envelope[SearchResult]: ...


class DraftTool(Protocol):
    def __call__(self, request: DraftInput) -> Envelope[Draft]: ...


class VerifyTool(Protocol):
    def __call__(self, request: VerifyInput) -> Envelope[Verification]: ...


class EmbeddingPort(Protocol):
    def __call__(self, request: EmbeddingInput) -> Envelope[EmbeddingOutput]: ...


class GenerationPort(Protocol):
    def __call__(self, request: GenerationInput) -> Envelope[GenerationOutput]: ...
