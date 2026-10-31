"""Inject tool implementations without changing other members' modules."""

from dataclasses import dataclass

from evidencedesk.assistant.tools import draft_answer, verify_answer
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


def build_tools(settings: Settings) -> Tools:
    if settings.app_mode != "mock":
        raise RuntimeError("Only APP_MODE=mock is implemented; live adapters are not ready.")
    return Tools(
        ingest=ingest_documents,
        sources=read_sources,
        search=search_passages,
        draft=draft_answer,
        verify=verify_answer,
    )
