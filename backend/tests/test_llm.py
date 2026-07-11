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


def test_ollama_beruecksichtigt_gespraechsverlauf(monkeypatch):
    aufrufe = {}

    def fake_post(url, json=None, timeout=None):
        aufrufe["prompt"] = json["prompt"]
        return httpx.Response(200, json={"response": "ok"},
                              request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    provider = OllamaProvider("http://localhost:11434", "llama3.1:8b")
    verlauf = [
        {"rolle": "nutzer", "text": "Wo ist das Rathaus?"},
        {"rolle": "bot", "text": "Am Marktplatz."},
    ]
    provider.antworte("Und die Öffnungszeiten?", TREFFER, "Demo GmbH", verlauf)
    assert "Wo ist das Rathaus?" in aufrufe["prompt"]
    assert "Am Marktplatz." in aufrufe["prompt"]


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


def test_extractive_stream_liefert_gesamtantwort():
    stuecke = list(ExtractiveProvider().antworte_stream("Frage", TREFFER, "Demo GmbH"))
    assert "urlaubsregelung" in "".join(stuecke)


class _FakeStreamResponse:
    def __init__(self, zeilen):
        self._zeilen = zeilen

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def raise_for_status(self):
        pass

    def iter_lines(self):
        yield from self._zeilen


def test_ollama_streaming(monkeypatch):
    zeilen = [
        '{"response": "Urlaub wird ", "done": false}',
        '{"response": "digital beantragt.", "done": false}',
        '{"response": "", "done": true}',
    ]
    monkeypatch.setattr(
        httpx, "stream", lambda *a, **k: _FakeStreamResponse(zeilen)
    )
    provider = OllamaProvider("http://localhost:11434", "llama3.1:8b")
    stuecke = list(provider.antworte_stream("Wie beantrage ich Urlaub?", TREFFER, "Demo GmbH"))
    assert stuecke == ["Urlaub wird ", "digital beantragt."]


def test_ollama_streaming_fallback(monkeypatch):
    def kaputt(*a, **k):
        raise httpx.ConnectError("Verbindung abgelehnt")

    monkeypatch.setattr(httpx, "stream", kaputt)
    provider = OllamaProvider("http://localhost:11434", "llama3.1:8b")
    stuecke = list(provider.antworte_stream("Wie beantrage ich Urlaub?", TREFFER, "Demo GmbH"))
    assert "urlaubsregelung" in "".join(stuecke)
