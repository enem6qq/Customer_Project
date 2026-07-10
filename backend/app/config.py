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
    # "bm25" (Volltext, ohne Zusatzpakete) oder "hybrid" (BM25 + Embeddings;
    # benötigt: pip install -r requirements-embeddings.txt)
    provider: str = "bm25"
    # Mehrsprachiges Modell, läuft lokal auf CPU – gut für deutsche Fragen.
    embedding_model: str = "intfloat/multilingual-e5-small"
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
    # "team"   = Login + Benutzerrechte (Standard für Unternehmen)
    # "privat" = kein Login, alle Dokumente sichtbar – für die lokale,
    #            persönliche Nutzung auf dem eigenen Rechner
    modus: str = "team"
    # Ablage alle N Sekunden auf neue/geänderte Dateien prüfen und dann
    # automatisch neu indizieren. 0 = aus (nur beim Start / per Reindex-API).
    auto_reindex_sekunden: int = 30
    llm: LLMConfig = Field(default_factory=LLMConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    # Ein Pfad oder eine Liste von Pfaden – relativ zum Projekt oder absolut
    # (z. B. "C:/Ablage/Vertraege" oder "/mnt/ablage"). Alle Ordner werden
    # gemeinsam indiziert.
    dokumente_pfad: str | list[str] = "data/documents"
    ansprechpartner: list[Ansprechpartner] = Field(default_factory=list)

    @property
    def dokumente_verzeichnisse(self) -> list[Path]:
        roh = self.dokumente_pfad if isinstance(self.dokumente_pfad, list) else [self.dokumente_pfad]
        verzeichnisse = []
        for eintrag in roh:
            pfad = Path(str(eintrag)).expanduser()
            verzeichnisse.append(pfad if pfad.is_absolute() else REPO_ROOT / pfad)
        return verzeichnisse


class Settings(BaseModel):
    tenant: TenantConfig
    users_file: Path
    jwt_secret: str
    jwt_ttl_minutes: int = 480
    # Nutzer-Feedback (👍/👎) landet als JSON-Zeilen in dieser Datei.
    feedback_datei: Path = REPO_ROOT / "data" / "feedback.jsonl"


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
    tenant = _load_tenant(tenant_path)
    # Eigenen Dokumentenordner ohne Konfigurationsänderung nutzen, z. B.:
    #   DOCUMENTS_PATH=~/Dokumente ./start.sh privat
    dokumente_env = os.environ.get("DOCUMENTS_PATH", "")
    if dokumente_env:
        tenant.dokumente_pfad = str(Path(dokumente_env).expanduser())
    return Settings(
        tenant=tenant,
        users_file=users_path,
        jwt_secret=jwt_secret,
        jwt_ttl_minutes=int(os.environ.get("JWT_TTL_MINUTES", "480")),
        feedback_datei=Path(
            os.environ.get("FEEDBACK_PATH", REPO_ROOT / "data" / "feedback.jsonl")
        ),
    )
