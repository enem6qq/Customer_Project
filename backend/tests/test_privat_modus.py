"""Privat-Modus: lokale Einzelnutzung ohne Login, alle Dokumente sichtbar."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings


@pytest.fixture()
def privat_client(tmp_path, monkeypatch):
    (tmp_path / "geheim").mkdir()
    (tmp_path / "geheim" / "notizen.md").write_text(
        "Meine Steuererklärung 2025 liegt im Ordner Finanzen.", encoding="utf-8"
    )
    tenant = tmp_path / "tenant.yaml"
    tenant.write_text(
        "unternehmen:\n  name: Meine private Ablage\nmodus: privat\n"
        f"dokumente_pfad: {tmp_path}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("TENANT_CONFIG", str(tenant))
    get_settings.cache_clear()

    from app.main import app

    with TestClient(app) as client:
        yield client

    get_settings.cache_clear()


def test_chat_ohne_login(privat_client):
    r = privat_client.post("/api/chat", json={"frage": "Wo liegt meine Steuererklärung?"})
    assert r.status_code == 200
    assert "Steuererklärung" in r.json()["antwort"]


def test_health_meldet_privatmodus(privat_client):
    body = privat_client.get("/api/health").json()
    assert body["modus"] == "privat"
    assert body["unternehmen"] == "Meine private Ablage"


def test_documents_path_umgebungsvariable(tmp_path, monkeypatch):
    """DOCUMENTS_PATH überschreibt den Dokumentenpfad aus der tenant.yaml."""
    eigener_ordner = tmp_path / "eigene_dokumente"
    eigener_ordner.mkdir()
    monkeypatch.setenv("DOCUMENTS_PATH", str(eigener_ordner))
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.tenant.dokumente_verzeichnis == eigener_ordner
    finally:
        get_settings.cache_clear()
