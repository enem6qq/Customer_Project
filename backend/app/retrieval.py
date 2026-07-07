"""Retrieval: Suche über die indizierten Chunks – immer mit RBAC-Filter.

Provider:
- "bm25":   Volltext-Relevanzsuche, keine Zusatzpakete, läuft überall.
- "hybrid": BM25 + semantische Embedding-Suche (lokales mehrsprachiges Modell),
            kombiniert per Reciprocal Rank Fusion. Findet auch Umschreibungen
            ("freie Tage" -> Urlaubsregelung). Benötigt:
            pip install -r requirements-embeddings.txt

Wichtig für den Datenschutz und die Berechtigungen: Der Filter nach
Zugriffsgruppen passiert HIER, vor jeder LLM-Anfrage. Chunks, die der
Benutzer nicht sehen darf, verlassen diese Schicht nicht.
"""

from __future__ import annotations

import logging
import math
import re
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass

from rank_bm25 import BM25Okapi

from .auth import User
from .config import RetrievalConfig
from .ingestion import Chunk

logger = logging.getLogger(__name__)

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
        self._token_sets: list[set[str]] = []
        self._bm25: BM25Okapi | None = None

    def index(self, chunks: list[Chunk]) -> None:
        self._chunks = chunks
        korpus = [tokenize(c.text + " " + c.titel) for c in chunks]
        self._token_sets = [set(tokens) for tokens in korpus]
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
        frage_tokens = set(tokens)
        treffer = [
            Treffer(chunk=chunk, score=float(score))
            for chunk, score, token_set in zip(self._chunks, scores, self._token_sets)
            # Relevanz über Token-Überlappung statt Score-Vorzeichen prüfen:
            # bei sehr kleinen Beständen liefert BM25 auch für echte Treffer
            # Scores <= 0 (negative IDF). RBAC-Filter: nur erlaubte Gruppen.
            if frage_tokens & token_set and user.darf_gruppe(chunk.gruppe)
        ]
        treffer.sort(key=lambda t: t.score, reverse=True)
        return treffer[:top_k]


# Eine Embedding-Funktion bildet Texte auf Vektoren ab. In Tests kann hier
# eine einfache Fake-Funktion übergeben werden, produktiv kommt
# sentence-transformers zum Einsatz (lazy geladen, damit die Basis-Installation
# ohne PyTorch auskommt).
EmbeddingFunktion = Callable[[list[str]], list[list[float]]]


def _lade_sentence_transformer(model_name: str) -> EmbeddingFunktion:
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError(
            "Für retrieval.provider = 'hybrid' bitte zuerst installieren: "
            "pip install -r backend/requirements-embeddings.txt "
            "(oder in tenant.yaml auf 'bm25' zurückstellen)."
        ) from exc
    modell = SentenceTransformer(model_name)

    def embed(texte: list[str]) -> list[list[float]]:
        return modell.encode(texte, normalize_embeddings=True).tolist()

    return embed


def _normalisiere(vektor: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vektor))
    return [x / norm for x in vektor] if norm > 0 else vektor


class VectorRetriever(Retriever):
    """Semantische Suche über Kosinus-Ähnlichkeit (In-Memory).

    E5-Modelle erwarten die Präfixe "query: " / "passage: " – die werden hier
    gesetzt; für andere Embedding-Funktionen sind sie unschädlich.
    """

    def __init__(self, embedder: EmbeddingFunktion):
        self._embedder = embedder
        self._chunks: list[Chunk] = []
        self._vektoren: list[list[float]] = []

    def index(self, chunks: list[Chunk]) -> None:
        self._chunks = chunks
        texte = [f"passage: {c.titel}\n{c.text}" for c in chunks]
        self._vektoren = [_normalisiere(v) for v in self._embedder(texte)] if texte else []

    def suche(self, frage: str, user: User, top_k: int = 5) -> list[Treffer]:
        if not self._vektoren:
            return []
        frage_vektor = _normalisiere(self._embedder([f"query: {frage}"])[0])
        treffer = [
            Treffer(chunk=chunk, score=sum(a * b for a, b in zip(frage_vektor, vektor)))
            for chunk, vektor in zip(self._chunks, self._vektoren)
            # RBAC: nur Chunks aus Gruppen, die der Benutzer sehen darf
            if user.darf_gruppe(chunk.gruppe)
        ]
        treffer.sort(key=lambda t: t.score, reverse=True)
        return treffer[:top_k]


class HybridRetriever(Retriever):
    """Kombiniert BM25 (exakte Begriffe) und Vektorsuche (Bedeutung) per
    Reciprocal Rank Fusion: score = Σ 1 / (K + Rang). Robust, ohne dass die
    Score-Skalen beider Verfahren vergleichbar sein müssten."""

    RRF_K = 60

    def __init__(self, embedder: EmbeddingFunktion):
        self._bm25 = BM25Retriever()
        self._vektor = VectorRetriever(embedder)

    def index(self, chunks: list[Chunk]) -> None:
        self._bm25.index(chunks)
        self._vektor.index(chunks)

    @property
    def anzahl_chunks(self) -> int:
        return self._bm25.anzahl_chunks

    def suche(self, frage: str, user: User, top_k: int = 5) -> list[Treffer]:
        # Beide Verfahren etwas breiter suchen, dann fusionieren.
        kandidaten_k = max(top_k * 3, 10)
        punkte: dict[int, float] = {}
        chunks: dict[int, Chunk] = {}
        for liste in (
            self._bm25.suche(frage, user, kandidaten_k),
            self._vektor.suche(frage, user, kandidaten_k),
        ):
            for rang, treffer in enumerate(liste):
                schluessel = id(treffer.chunk)
                punkte[schluessel] = punkte.get(schluessel, 0.0) + 1.0 / (self.RRF_K + rang + 1)
                chunks[schluessel] = treffer.chunk
        fusioniert = [Treffer(chunk=chunks[s], score=p) for s, p in punkte.items()]
        fusioniert.sort(key=lambda t: t.score, reverse=True)
        return fusioniert[:top_k]


def erstelle_retriever(
    config: RetrievalConfig,
    embedder: EmbeddingFunktion | None = None,
) -> Retriever:
    if config.provider == "bm25":
        return BM25Retriever()
    if config.provider == "hybrid":
        return HybridRetriever(embedder or _lade_sentence_transformer(config.embedding_model))
    raise ValueError(f"Unbekannter Retrieval-Provider: {config.provider!r}")
