"""End-to-End-Tests gegen die FastAPI-App mit der Demo-Konfiguration.

Getestet wird vor allem das Herzstück: die Rechteprüfung (RBAC) –
gleiche Frage, unterschiedliche Benutzer, unterschiedliche Ergebnisse.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def login(client, username, password):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["chunks"] > 0
    assert len(body["beispiel_fragen"]) > 0


def test_admin_stats(client):
    headers = login(client, "gast", "gast123")
    assert client.get("/api/admin/stats", headers=headers).status_code == 403

    headers = login(client, "admin", "admin123")
    r = client.get("/api/admin/stats", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["dokumente"] >= 4
    assert "finanzen" in body["gruppen"]
    assert body["feedback"].keys() == {"gut", "schlecht"}


def test_admin_seite_wird_ausgeliefert(client):
    r = client.get("/admin")
    assert r.status_code == 200
    assert "Admin-Dashboard" in r.text


def test_login_falsches_passwort(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "falsch"})
    assert r.status_code == 401


def test_chat_ohne_token_verboten(client):
    r = client.post("/api/chat", json={"frage": "Wie beantrage ich Urlaub?"})
    assert r.status_code == 401


def test_admin_sieht_finanzdokumente(client):
    headers = login(client, "admin", "admin123")
    r = client.post("/api/chat", json={"frage": "Wie hoch ist das Budget 2026?"}, headers=headers)
    assert r.status_code == 200
    gruppen = {q["gruppe"] for q in r.json()["quellen"]}
    assert "finanzen" in gruppen


def test_gast_sieht_keine_finanzdokumente(client):
    """RBAC: Der Gast darf nur 'allgemein' – Finanz-Chunks dürfen nie auftauchen."""
    headers = login(client, "gast", "gast123")
    r = client.post("/api/chat", json={"frage": "Wie hoch ist das Budget 2026?"}, headers=headers)
    assert r.status_code == 200
    body = r.json()
    gruppen = {q["gruppe"] for q in body["quellen"]}
    assert "finanzen" not in gruppen
    assert "42,5" not in body["antwort"]  # vertraulicher Inhalt darf nicht durchsickern


def test_mitarbeiter_sieht_personal_aber_nicht_finanzen(client):
    headers = login(client, "mmuster", "demo123")
    r = client.post("/api/chat", json={"frage": "Wie viele Urlaubstage habe ich?"}, headers=headers)
    assert r.status_code == 200
    gruppen = {q["gruppe"] for q in r.json()["quellen"]}
    assert "personal" in gruppen

    r = client.get("/api/documents/search", params={"q": "Budget 2026"}, headers=headers)
    gruppen = {t["gruppe"] for t in r.json()["treffer"]}
    assert "finanzen" not in gruppen


def test_ansprechpartner_wird_gefunden(client):
    headers = login(client, "gast", "gast123")
    r = client.post("/api/chat", json={"frage": "An wen wende ich mich bei IT Problemen?"}, headers=headers)
    assert r.status_code == 200
    partner = r.json()["ansprechpartner"]
    assert any(a["bereich"] == "IT" for a in partner)


def test_quelle_enthaelt_pfad(client):
    headers = login(client, "admin", "admin123")
    r = client.post("/api/chat", json={"frage": "Wie hoch ist das Budget 2026?"}, headers=headers)
    quelle = r.json()["quellen"][0]
    assert quelle["pfad"].endswith("budgetplanung_2026.md")


def test_dokument_datei_mit_berechtigung(client):
    headers = login(client, "admin", "admin123")
    r = client.get(
        "/api/documents/file",
        params={"name": "finanzen/budgetplanung_2026.md"},
        headers=headers,
    )
    assert r.status_code == 200
    assert "42,5" in r.text


def test_dokument_datei_ohne_berechtigung_verboten(client):
    """RBAC gilt auch für den Datei-Abruf: gast darf kein Finanzdokument laden."""
    headers = login(client, "gast", "gast123")
    r = client.get(
        "/api/documents/file",
        params={"name": "finanzen/budgetplanung_2026.md"},
        headers=headers,
    )
    assert r.status_code == 403


def test_dokument_datei_nur_indizierte(client):
    """Nur indizierte Dokumente sind abrufbar – kein Path-Traversal möglich."""
    headers = login(client, "admin", "admin123")
    r = client.get(
        "/api/documents/file",
        params={"name": "../../config/users.yaml"},
        headers=headers,
    )
    assert r.status_code == 404


def test_chat_stream(client):
    import json

    headers = login(client, "gast", "gast123")
    with client.stream(
        "POST", "/api/chat/stream",
        json={"frage": "Wie melde ich eine IT Störung?"},
        headers=headers,
    ) as r:
        assert r.status_code == 200
        ereignisse = [json.loads(z) for z in r.iter_lines() if z.strip()]
    assert ereignisse[0]["typ"] == "meta"
    assert len(ereignisse[0]["quellen"]) > 0
    tokens = [e for e in ereignisse if e["typ"] == "token"]
    assert tokens and "Wissensdatenbank" in "".join(t["text"] for t in tokens)
    assert ereignisse[-1]["typ"] == "ende"


def test_chat_stream_rbac(client):
    """Auch im Stream: gast bekommt keine Finanz-Quellen."""
    import json

    headers = login(client, "gast", "gast123")
    with client.stream(
        "POST", "/api/chat/stream",
        json={"frage": "Wie hoch ist das Budget 2026?"},
        headers=headers,
    ) as r:
        ereignisse = [json.loads(z) for z in r.iter_lines() if z.strip()]
    gruppen = {q["gruppe"] for q in ereignisse[0]["quellen"]}
    assert "finanzen" not in gruppen
    assert "42,5" not in "".join(e.get("text", "") for e in ereignisse)


def test_chat_stream_ohne_token_verboten(client):
    r = client.post("/api/chat/stream", json={"frage": "Test"})
    assert r.status_code == 401


def test_chat_mit_verlauf(client):
    headers = login(client, "gast", "gast123")
    r = client.post(
        "/api/chat",
        json={
            "frage": "Und wie sind die Öffnungszeiten?",
            "verlauf": [
                {"rolle": "nutzer", "text": "Wo ist das Rathaus?"},
                {"rolle": "bot", "text": "Am Marktplatz."},
            ],
        },
        headers=headers,
    )
    assert r.status_code == 200


def test_reindex_nur_fuer_admin(client):
    headers = login(client, "gast", "gast123")
    assert client.post("/api/admin/reindex", headers=headers).status_code == 403
    headers = login(client, "admin", "admin123")
    r = client.post("/api/admin/reindex", headers=headers)
    assert r.status_code == 200
    assert r.json()["chunks"] > 0
