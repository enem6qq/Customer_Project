"""LLM-Provider – austauschbar per Konfiguration.

- extractive:          Kein LLM. Gibt die relevantesten Fundstellen strukturiert
                       zurück. Läuft überall, ideal für erste Demos und als
                       Fallback, wenn kein Modell erreichbar ist.
- ollama:              Lokales LLM über Ollama (http://localhost:11434) –
                       maximale Datenhoheit, nichts verlässt den eigenen Server.
- openai_compatible:   Beliebiger OpenAI-kompatibler Endpunkt. Für DSGVO-konforme
                       Setups einen EU-/DE-Anbieter wählen (z. B. IONOS AI Model
                       Hub, STACKIT) und dies vertraglich (AVV) absichern.
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod

import httpx

from .config import LLMConfig
from .retrieval import Treffer

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Du bist der interne Wissensassistent von {unternehmen}. "
    "Beantworte die Frage AUSSCHLIESSLICH auf Basis der folgenden Auszüge aus "
    "internen Dokumenten. Wenn die Auszüge keine Antwort hergeben, sage ehrlich, "
    "dass du dazu nichts in der Wissensdatenbank gefunden hast, und schlage vor, "
    "den zuständigen Ansprechpartner zu kontaktieren. Antworte auf Deutsch, "
    "präzise und ohne Spekulation. Nenne am Ende die verwendeten Dokumente."
)


def baue_kontext(treffer: list[Treffer]) -> str:
    teile = []
    for i, t in enumerate(treffer, start=1):
        teile.append(f"[Auszug {i} – Dokument: {t.chunk.dokument}]\n{t.chunk.text}")
    return "\n\n".join(teile)


class LLMProvider(ABC):
    @abstractmethod
    def antworte(self, frage: str, treffer: list[Treffer], unternehmen: str) -> str: ...


class ExtractiveProvider(LLMProvider):
    """Antwort ohne LLM: die besten Fundstellen, sauber formatiert."""

    def antworte(self, frage: str, treffer: list[Treffer], unternehmen: str) -> str:
        if not treffer:
            return (
                "Dazu habe ich in der Wissensdatenbank nichts gefunden. "
                "Bitte wenden Sie sich an den zuständigen Ansprechpartner."
            )
        zeilen = ["Das habe ich in der Wissensdatenbank gefunden:\n"]
        for t in treffer:
            auszug = t.chunk.text.strip()
            if len(auszug) > 500:
                auszug = auszug[:500].rsplit(" ", 1)[0] + " …"
            zeilen.append(f"**{t.chunk.titel}** (`{t.chunk.dokument}`):\n{auszug}\n")
        zeilen.append(
            "_Hinweis: Es ist kein Sprachmodell konfiguriert – dies sind die "
            "relevantesten Originalauszüge._"
        )
        return "\n".join(zeilen)


class OllamaProvider(LLMProvider):
    def __init__(self, base_url: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.model = model

    def antworte(self, frage: str, treffer: list[Treffer], unternehmen: str) -> str:
        prompt = (
            SYSTEM_PROMPT.format(unternehmen=unternehmen)
            + "\n\n--- Dokumentauszüge ---\n"
            + baue_kontext(treffer)
            + f"\n\n--- Frage ---\n{frage}"
        )
        try:
            response = httpx.post(
                f"{self.base_url}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False},
                timeout=120,
            )
            response.raise_for_status()
            return response.json().get("response", "").strip()
        except httpx.HTTPError:
            logger.exception("Ollama nicht erreichbar – falle auf extraktive Antwort zurück")
            return ExtractiveProvider().antworte(frage, treffer, unternehmen)


class OpenAICompatibleProvider(LLMProvider):
    def __init__(self, base_url: str, model: str, api_key_env: str):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = os.environ.get(api_key_env, "")

    def antworte(self, frage: str, treffer: list[Treffer], unternehmen: str) -> str:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT.format(unternehmen=unternehmen)},
                        {
                            "role": "user",
                            "content": "--- Dokumentauszüge ---\n"
                            + baue_kontext(treffer)
                            + f"\n\n--- Frage ---\n{frage}",
                        },
                    ],
                    "temperature": 0.2,
                },
                timeout=120,
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"].strip()
        except (httpx.HTTPError, KeyError, IndexError):
            logger.exception("LLM-Endpunkt nicht erreichbar – falle auf extraktive Antwort zurück")
            return ExtractiveProvider().antworte(frage, treffer, unternehmen)


def erstelle_llm(config: LLMConfig) -> LLMProvider:
    if config.provider == "extractive":
        return ExtractiveProvider()
    if config.provider == "ollama":
        return OllamaProvider(config.ollama.base_url, config.ollama.model)
    if config.provider == "openai_compatible":
        c = config.openai_compatible
        return OpenAICompatibleProvider(c.base_url, c.model, c.api_key_env)
    raise ValueError(f"Unbekannter LLM-Provider: {config.provider!r}")
