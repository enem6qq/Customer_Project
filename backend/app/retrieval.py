"""Retrieval: Suche über die indizierten Chunks – immer mit RBAC-Filter.

Standard-Provider ist BM25 (schlanke Volltext-Relevanzsuche ohne externe
Dienste). Eine Vektor-/Embedding-Suche kann als weiterer `Retriever`
implementiert und in der tenant.yaml ausgewählt werden, ohne dass sich die
API ändert.

Wichtig für den Datenschutz und die Berechtigungen: Der Filter nach
Zugriffsgruppen passiert HIER, vor jeder LLM-Anfrage. Chunks, die der
Benutzer nicht sehen darf, verlassen diese Schicht nicht.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

from rank_bm25 import BM25Okapi

from .auth import User
from .ingestion import Chunk

_TOKEN_RE = re.compile(r"[a-zA-Z0-9äöüÄÖÜß]+")

# Sehr häufige deutsche Funktionswörter, die für die Relevanz nichts beitragen.
_STOPWOERTER = {
    "der", "die", "das", "und", "oder", "ein", "eine", "einen", "einem", "einer",
    "ich", "wie", "was", "wer", "wo", "wann", "ist", "sind", "war", "hat", "haben",
    "kann", "muss", "für", "von", "mit", "auf", "aus", "bei", "nach", "zu", "zum",
    "zur", "in", "im", "an", "am", "es", "sich", "nicht", "auch", "werden", "wird",
    "man", "mein", "meine", "unser", "ihre", "gibt",
}


def tokenize(text: str) -> list[str]:
    tokens = [t.lower() for t in _TOKEN_RE.findall(text)]
    return [t for t in tokens if t not in _STOPWOERTER]


@dataclass
class Treffer:
    chunk: Chunk
    score: float


class Retriever(ABC):
    @abstractmethod
    def index(self, chunks: list[Chunk]) -> None: ...

    @abstractmethod
    def suche(self, frage: str, user: User, top_k: int = 5) -> list[Treffer]: ...


class BM25Retriever(Retriever):
    def __init__(self) -> None:
        self._chunks: list[Chunk] = []
        self._bm25: BM25Okapi | None = None

    def index(self, chunks: list[Chunk]) -> None:
        self._chunks = chunks
        korpus = [tokenize(c.text + " " + c.titel) for c in chunks]
        self._bm25 = BM25Okapi(korpus) if korpus else None

    @property
    def anzahl_chunks(self) -> int:
        return len(self._chunks)

    def suche(self, frage: str, user: User, top_k: int = 5) -> list[Treffer]:
        if self._bm25 is None:
            return []
        tokens = tokenize(frage)
        if not tokens:
            return []
        scores = self._bm25.get_scores(tokens)
        treffer = [
            Treffer(chunk=chunk, score=float(score))
            for chunk, score in zip(self._chunks, scores)
            # RBAC: nur Chunks aus Gruppen, die der Benutzer sehen darf
            if score > 0 and user.darf_gruppe(chunk.gruppe)
        ]
        treffer.sort(key=lambda t: t.score, reverse=True)
        return treffer[:top_k]


def erstelle_retriever(provider: str) -> Retriever:
    if provider == "bm25":
        return BM25Retriever()
    raise ValueError(f"Unbekannter Retrieval-Provider: {provider!r}")
