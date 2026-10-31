"""Inject tool implementations without changing other members' modules."""

from collections.abc import Callable
from dataclasses import dataclass

import httpx

from evidencedesk.assistant.tools import draft_answer, verify_answer
from evidencedesk.contracts.models import Health
from evidencedesk.contracts.ports import DraftTool, IngestTool, SearchTool, SourcesTool, VerifyTool
from evidencedesk.core.settings import Settings
from evidencedesk.ingestion.tools import ingest_documents, read_sources
from evidencedesk.retrieval.tools import search_passages


@dataclass(frozen=True)
class Tools:
    ingest: IngestTool
    sources: SourcesTool
    search: SearchTool
    draft: DraftTool
    verify: VerifyTool
    health: Callable[[], Health] | None = None
    close: Callable[[], None] | None = None


def build_tools(settings: Settings) -> Tools:
    if settings.app_mode == "live":
        return _build_live_tools(settings)
    if settings.app_mode != "mock":
        raise RuntimeError("APP_MODE must be mock or live.")
    return Tools(
        ingest=ingest_documents,
        sources=read_sources,
        search=search_passages,
        draft=draft_answer,
        verify=verify_answer,
    )


def _build_live_tools(settings: Settings) -> Tools:
    from evidencedesk.assistant.drafting import GroundedDraftAnswer
    from evidencedesk.assistant.generation import GENERATION_MODEL, OllamaGeneration
    from evidencedesk.assistant.verification import GroundedVerifier
    from evidencedesk.ingestion.live import LiveIngestion
    from evidencedesk.retrieval.embeddings import EMBEDDING_MODEL, OllamaEmbeddings
    from evidencedesk.retrieval.index import QdrantIndex
    from evidencedesk.retrieval.projection import CompactEmbeddings

    if (settings.generation_model, settings.embedding_model) != (GENERATION_MODEL, EMBEDDING_MODEL):
        raise RuntimeError("Live mode requires qwen3:4b and nomic-embed-text:v1.5.")
    client = httpx.Client(
        base_url=settings.ollama_base_url, timeout=httpx.Timeout(240, connect=3), trust_env=False
    )
    try:
        index = QdrantIndex(settings.qdrant_path, CompactEmbeddings(OllamaEmbeddings(client)))
    except Exception:
        client.close()
        raise
    generation = OllamaGeneration(client)

    def health() -> Health:
        available = False
        try:
            response = client.get("/api/tags", timeout=2)
            response.raise_for_status()
            models = {entry["name"] for entry in response.json()["models"]}
            available = {GENERATION_MODEL, EMBEDDING_MODEL} <= models
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            pass
        return Health(
            mode="live",
            ready=index.ready and available,
            ollama_available=available,
            generation_model=settings.generation_model,
            embedding_model=settings.embedding_model,
            index_revision=index.index_revision,
            document_count=index.document_count,
        )

    def close() -> None:
        try:
            index.close()
        finally:
            client.close()

    return Tools(
        ingest=LiveIngestion(index),
        sources=index.read_sources,
        search=index.search,
        draft=GroundedDraftAnswer(generation),
        verify=GroundedVerifier(generation),
        health=health,
        close=close,
    )
