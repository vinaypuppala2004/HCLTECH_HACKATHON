"""Read shared configuration without requiring any external services."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Settings:
    app_mode: str = "mock"
    backend_url: str = "http://127.0.0.1:8000"
    ollama_base_url: str = "http://127.0.0.1:11434"
    generation_model: str = "qwen3:4b"
    embedding_model: str = "nomic-embed-text:v1.5"
    qdrant_path: str = "./var/qdrant"


def get_settings() -> Settings:
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    return Settings(
        app_mode=os.getenv("APP_MODE", "mock"),
        backend_url=os.getenv("BACKEND_URL", "http://127.0.0.1:8000").rstrip("/"),
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
        generation_model=os.getenv("GENERATION_MODEL", "qwen3:4b"),
        embedding_model=os.getenv("EMBEDDING_MODEL", "nomic-embed-text:v1.5"),
        qdrant_path=os.getenv("QDRANT_PATH", "./var/qdrant"),
    )
