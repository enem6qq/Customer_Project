"""Tests für BM25-, Vektor- und Hybrid-Suche inkl. RBAC-Filter.

Die Embedding-Funktion wird hier durch eine deterministische Fake-Funktion
ersetzt, damit die Tests ohne PyTorch/Modell-Download laufen. Die echte
sentence-transformers-Anbindung hat dieselbe Schnittstelle.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.auth import User
from app.config import RetrievalConfig
from app.ingestion import Chunk
from app.retrieval import (
    BM25Retriever,
    HybridRetriever,
    VectorRetriever,
    erstelle_retriever,
)

# Fake-Embeddings: feste "Themenachsen" (Urlaub, IT, Finanzen) – Texte mit
# passenden Schlüsselwörtern bekommen einen Vektor nahe der jeweiligen Achse.
THEMEN = {
    "urlaub": 0, "erholung": 0, "freistellung": 0,
    "computer": 1, "laptop": 1, "störung": 1,
    "budget": 2, "geld": 2, "finanzen": 2,
}


def fake_embedder(texte):
    vektoren = []
    for text in texte:
        v = [0.01, 0.01, 0.01]
        for wort, achse in THEMEN.items():
            if wort in text.lower():
                v[achse] += 1.0
        vektoren.append(v)
    return vektoren


def chunk(text, gruppe="allgemein", titel="doc"):
    return Chunk(text=text, dokument=f"{gruppe}/{titel}.md", titel=titel, gruppe=gruppe, position=0)


CHUNKS = [
    chunk("Anspruch auf Erholung und Freistellung: 30 Tage.", "personal", "urlaubsregelung"),
    chunk("Bei defektem Laptop oder Computer bitte Ticket öffnen.", "allgemein", "it_hilfe"),
    chunk("Das Budget umfasst 42 Mio. Geld für Finanzen.", "finanzen", "budget"),
]

ALLES = User(username="a", gruppen=["*"])
NUR_ALLGEMEIN = User(username="g", gruppen=["allgemein"])


def test_vektor_findet_umschreibung():
    """Semantik: 'Urlaub' steht nicht im Text – die Bedeutungsachse trifft trotzdem."""
    r = VectorRetriever(fake_embedder)
    r.index(CHUNKS)
    treffer = r.suche("Wie viel Urlaub bekomme ich?", ALLES, top_k=1)
    assert treffer[0].chunk.titel == "urlaubsregelung"


def test_bm25_findet_umschreibung_nicht():
    """Gegenprobe: reine Volltextsuche scheitert an der Umschreibung."""
    r = BM25Retriever()
    r.index(CHUNKS)
    treffer = r.suche("Wie viel Urlaub bekomme ich?", ALLES, top_k=1)
    assert not treffer or treffer[0].chunk.titel != "urlaubsregelung"


def test_hybrid_kombiniert_beide_verfahren():
    r = HybridRetriever(fake_embedder)
    r.index(CHUNKS)
    # Semantischer Treffer (nur über Embeddings erreichbar)
    assert r.suche("Wie viel Urlaub bekomme ich?", ALLES, 1)[0].chunk.titel == "urlaubsregelung"
    # Exakter Begriff (klassische BM25-Stärke)
    assert r.suche("Ticket öffnen", ALLES, 1)[0].chunk.titel == "it_hilfe"


def test_hybrid_respektiert_rbac():
    r = HybridRetriever(fake_embedder)
    r.index(CHUNKS)
    treffer = r.suche("Wie hoch ist das Budget an Geld für Finanzen?", NUR_ALLGEMEIN, top_k=5)
    assert all(t.chunk.gruppe == "allgemein" for t in treffer)


def test_erstelle_retriever_hybrid_mit_eigenem_embedder():
    r = erstelle_retriever(RetrievalConfig(provider="hybrid"), embedder=fake_embedder)
    assert isinstance(r, HybridRetriever)


def test_erstelle_retriever_unbekannt():
    with pytest.raises(ValueError):
        erstelle_retriever(RetrievalConfig(provider="quantenglaskugel"))


def test_vektor_datenbank_cache(tmp_path):
    """Zweiter Index-Lauf holt alle Embeddings aus der SQLite-Datenbank."""
    from app.retrieval import VektorDatenbank

    aufrufe = {"anzahl": 0}

    def zaehlender_embedder(texte):
        aufrufe["anzahl"] += len(texte)
        return fake_embedder(texte)

    db_pfad = tmp_path / "vektoren.sqlite"

    r1 = VectorRetriever(zaehlender_embedder, VektorDatenbank(db_pfad, "test-modell"))
    r1.index(CHUNKS)
    assert aufrufe["anzahl"] == len(CHUNKS)

    # Neuer Retriever (wie nach Neustart), gleiche Datenbank: 0 neue Berechnungen
    r2 = VectorRetriever(zaehlender_embedder, VektorDatenbank(db_pfad, "test-modell"))
    r2.index(CHUNKS)
    assert aufrufe["anzahl"] == len(CHUNKS)

    # Suche funktioniert mit Vektoren aus der Datenbank
    treffer = r2.suche("Wie viel Urlaub bekomme ich?", ALLES, top_k=1)
    assert treffer[0].chunk.titel == "urlaubsregelung"


def test_vektor_datenbank_neuer_text_wird_berechnet(tmp_path):
    from app.retrieval import VektorDatenbank

    aufrufe = {"anzahl": 0}

    def zaehlender_embedder(texte):
        aufrufe["anzahl"] += len(texte)
        return fake_embedder(texte)

    datenbank = VektorDatenbank(tmp_path / "v.sqlite", "test-modell")
    r = VectorRetriever(zaehlender_embedder, datenbank)
    r.index(CHUNKS)
    vorher = aufrufe["anzahl"]

    r.index(CHUNKS + [chunk("Ganz neuer Inhalt über Kantinen.", "allgemein", "kantine")])
    assert aufrufe["anzahl"] == vorher + 1  # nur der neue Chunk wurde berechnet
