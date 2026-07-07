"""LLM-Provider-Tests: Ollama-Anbindung (gemockt) und Fallback-Verhalten."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

from app.auth import User  # noqa: F401  (Import prüft Modulverdrahtung)
from app.ingestion import Chunk
from app.llm import ExtractiveProvider, OllamaProvider
from app.retrieval import Treffer

TREFFER = [
    Treffer(
        chunk=Chunk(
            text="Urlaub wird über das Zeitwirtschaftssystem beantragt.",
            dokument="personal/urlaubsregelung.md",
            titel="urlaubsregelung",
            gruppe="personal",
            position=0,
        ),
        score=1.0,
    )
]


def test_ollama_sendet_kontext_und_gibt_antwort_zurueck(monkeypatch):
    aufrufe = {}

    def fake_post(url, json=None, timeout=None):
        aufrufe["url"] = url
        aufrufe["prompt"] = json["prompt"]
        request = httpx.Request("POST", url)
        return httpx.Response(200, json={"response": "Über das Zeitwirtschaftssystem."},
                              request=request)

    monkeypatch.setattr(httpx, "post", fake_post)
    provider = OllamaProvider("http://localhost:11434", "llama3.1:8b")
    antwort = provider.antworte("Wie beantrage ich Urlaub?", TREFFER, "Demo GmbH")

    assert antwort == "Über das Zeitwirtschaftssystem."
    assert aufrufe["url"] == "http://localhost:11434/api/generate"
    # Der Dokumentkontext und die Frage müssen im Prompt ankommen
    assert "Zeitwirtschaftssystem" in aufrufe["prompt"]
    assert "Wie beantrage ich Urlaub?" in aufrufe["prompt"]
    assert "Demo GmbH" in aufrufe["prompt"]


def test_ollama_fallback_wenn_nicht_erreichbar(monkeypatch):
    def fake_post(url, json=None, timeout=None):
        raise httpx.ConnectError("Verbindung abgelehnt")

    monkeypatch.setattr(httpx, "post", fake_post)
    provider = OllamaProvider("http://localhost:11434", "llama3.1:8b")
    antwort = provider.antworte("Wie beantrage ich Urlaub?", TREFFER, "Demo GmbH")
    # Statt eines Fehlers kommt die extraktive Antwort mit den Fundstellen
    assert "urlaubsregelung" in antwort


def test_extractive_ohne_treffer():
    antwort = ExtractiveProvider().antworte("Irgendwas", [], "Demo GmbH")
    assert "nichts gefunden" in antwort
