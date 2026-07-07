"""Zentrale Konfiguration.

Alles Unternehmensspezifische (Mandant/Tenant) liegt in einer YAML-Datei,
Geheimnisse ausschließlich in Umgebungsvariablen. So kann dasselbe Grundgerüst
ohne Codeänderung für ein neues Unternehmen ausgerollt werden.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_TENANT_CONFIG = REPO_ROOT / "config" / "tenant.yaml"
DEFAULT_USERS_CONFIG = REPO_ROOT / "config" / "users.yaml"


class OllamaConfig(BaseModel):
    base_url: str = "http://localhost:11434"
    model: str = "llama3.1:8b"


class OpenAICompatibleConfig(BaseModel):
    base_url: str = ""
    model: str = ""
    # Name der Umgebungsvariable, die den API-Key enthält (nie der Key selbst!)
    api_key_env: str = "LLM_API_KEY"


class LLMConfig(BaseModel):
    # "extractive" (ohne LLM), "ollama" (lokal) oder "openai_compatible" (EU-Endpunkt)
    provider: str = "extractive"
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    openai_compatible: OpenAICompatibleConfig = Field(default_factory=OpenAICompatibleConfig)


class RetrievalConfig(BaseModel):
    provider: str = "bm25"
    chunk_size: int = 800
    chunk_overlap: int = 150
    top_k: int = 5


class Ansprechpartner(BaseModel):
    bereich: str
    name: str
    email: str = ""
    telefon: str = ""


class UnternehmenConfig(BaseModel):
    name: str = "Demo GmbH"
    sprache: str = "de"


class TenantConfig(BaseModel):
    unternehmen: UnternehmenConfig = Field(default_factory=UnternehmenConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    dokumente_pfad: str = "data/documents"
    ansprechpartner: list[Ansprechpartner] = Field(default_factory=list)

    @property
    def dokumente_verzeichnis(self) -> Path:
        pfad = Path(self.dokumente_pfad)
        return pfad if pfad.is_absolute() else REPO_ROOT / pfad


class Settings(BaseModel):
    tenant: TenantConfig
    users_file: Path
    jwt_secret: str
    jwt_ttl_minutes: int = 480


def _load_tenant(path: Path) -> TenantConfig:
    if not path.exists():
        return TenantConfig()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return TenantConfig.model_validate(raw)


@lru_cache
def get_settings() -> Settings:
    tenant_path = Path(os.environ.get("TENANT_CONFIG", DEFAULT_TENANT_CONFIG))
    users_path = Path(os.environ.get("USERS_CONFIG", DEFAULT_USERS_CONFIG))
    jwt_secret = os.environ.get("JWT_SECRET", "")
    if not jwt_secret:
        # Für die lokale Demo tolerierbar – im Betrieb MUSS JWT_SECRET gesetzt sein.
        jwt_secret = "nur-fuer-lokale-entwicklung-aendern"
    return Settings(
        tenant=_load_tenant(tenant_path),
        users_file=users_path,
        jwt_secret=jwt_secret,
        jwt_ttl_minutes=int(os.environ.get("JWT_TTL_MINUTES", "480")),
    )
