"""Feedback-Endpunkt (👍/👎) und Auto-Reindex-Signatur."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FEEDBACK_PATH", str(tmp_path / "feedback.jsonl"))
    get_settings.cache_clear()

    from app.main import app

    with TestClient(app) as c:
        yield c

    get_settings.cache_clear()


def login(client, username, password):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    return {"Authorization": "Bearer " + r.json()["token"]}


def test_feedback_wird_gespeichert(client, tmp_path):
    headers = login(client, "gast", "gast123")
    r = client.post(
        "/api/feedback",
        json={"frage": "Testfrage?", "antwort": "Testantwort.", "bewertung": "gut"},
        headers=headers,
    )
    assert r.status_code == 200
    zeilen = (tmp_path / "feedback.jsonl").read_text(encoding="utf-8").splitlines()
    eintrag = json.loads(zeilen[0])
    assert eintrag["benutzer"] == "gast"
    assert eintrag["bewertung"] == "gut"
    assert eintrag["frage"] == "Testfrage?"


def test_feedback_ungueltige_bewertung(client):
    headers = login(client, "gast", "gast123")
    r = client.post(
        "/api/feedback",
        json={"frage": "F", "antwort": "A", "bewertung": "super"},
        headers=headers,
    )
    assert r.status_code == 422


def test_feedback_liste_nur_admin(client):
    headers = login(client, "gast", "gast123")
    client.post(
        "/api/feedback",
        json={"frage": "F", "antwort": "A", "bewertung": "schlecht"},
        headers=headers,
    )
    assert client.get("/api/admin/feedback", headers=headers).status_code == 403

    admin = login(client, "admin", "admin123")
    r = client.get("/api/admin/feedback", headers=admin)
    assert r.status_code == 200
    assert r.json()["eintraege"][0]["bewertung"] == "schlecht"


def test_dokumente_signatur_erkennt_aenderungen(tmp_path):
    from app.main import _dokumente_signatur

    (tmp_path / "a.md").write_text("Inhalt", encoding="utf-8")
    vorher = _dokumente_signatur([tmp_path])

    (tmp_path / "b.md").write_text("Neu", encoding="utf-8")
    nach_neu = _dokumente_signatur([tmp_path])
    assert nach_neu != vorher

    (tmp_path / "b.md").unlink()
    nach_loeschen = _dokumente_signatur([tmp_path])
    assert nach_loeschen == vorher
