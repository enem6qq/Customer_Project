"""Dokumenten-Ingestion.

Liest Dokumente aus dem Ablageverzeichnis ein und zerlegt sie in Chunks.
Der oberste Ordnername unterhalb des Ablageverzeichnisses ist die
Zugriffsgruppe des Dokuments (z. B. data/documents/personal/urlaub.md
-> Gruppe "personal"). Dateien direkt im Wurzelverzeichnis gehören zur
Gruppe "allgemein".

Unterstützte Formate: .txt, .md, .pdf, .docx
Weitere Quellen (SharePoint, Netzlaufwerke, E-Mail-Postfächer) werden später
als zusätzliche Loader ergänzt – die Chunk-Struktur bleibt gleich.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

STANDARD_GRUPPE = "allgemein"


@dataclass
class Chunk:
    text: str
    dokument: str          # Anzeige-/Suchname (relativ zum Ablageverzeichnis)
    titel: str             # Dateiname ohne Endung
    gruppe: str            # Zugriffsgruppe (RBAC)
    position: int          # laufende Nummer innerhalb des Dokuments
    pfad_absolut: str = "" # Originaldatei auf der Platte (für Öffnen/Kopieren)
    metadata: dict = field(default_factory=dict)


def _read_txt(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _read_pdf(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return "\n\n".join((page.extract_text() or "") for page in reader.pages)


def _read_docx(path: Path) -> str:
    import docx

    document = docx.Document(str(path))
    parts = [p.text for p in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            parts.append(" | ".join(cell.text for cell in row.cells))
    return "\n".join(parts)


LOADERS = {
    ".txt": _read_txt,
    ".md": _read_txt,
    ".pdf": _read_pdf,
    ".docx": _read_docx,
}


def split_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Zerlegt Text an Absatzgrenzen in Chunks von ca. `chunk_size` Zeichen."""
    absaetze = [a.strip() for a in text.split("\n\n") if a.strip()]
    chunks: list[str] = []
    aktuell = ""
    for absatz in absaetze:
        if aktuell and len(aktuell) + len(absatz) + 2 > chunk_size:
            chunks.append(aktuell)
            # Überlappung: Ende des letzten Chunks als Kontext mitnehmen
            aktuell = aktuell[-overlap:] if overlap > 0 else ""
        aktuell = (aktuell + "\n\n" + absatz).strip() if aktuell else absatz
        # Sehr lange Absätze hart teilen
        while len(aktuell) > chunk_size:
            chunks.append(aktuell[:chunk_size])
            aktuell = aktuell[chunk_size - overlap:] if overlap > 0 else aktuell[chunk_size:]
    if aktuell:
        chunks.append(aktuell)
    return chunks


def lade_dokumente(
    basis: Path | list[Path], chunk_size: int = 800, overlap: int = 150
) -> list[Chunk]:
    basen = basis if isinstance(basis, list) else [basis]
    chunks: list[Chunk] = []
    mehrere_basen = len(basen) > 1

    for basis_pfad in basen:
        if not basis_pfad.exists():
            logger.warning("Dokumentenverzeichnis %s existiert nicht", basis_pfad)
            continue
        for datei in sorted(basis_pfad.rglob("*")):
            if not datei.is_file() or datei.suffix.lower() not in LOADERS:
                continue
            relativ = datei.relative_to(basis_pfad)
            gruppe = relativ.parts[0] if len(relativ.parts) > 1 else STANDARD_GRUPPE
            # Bei mehreren Ablageorten den Ordnernamen voranstellen, damit die
            # Anzeige eindeutig bleibt (z. B. "Vertraege/kunde_a/vertrag.pdf").
            name = f"{basis_pfad.name}/{relativ.as_posix()}" if mehrere_basen else relativ.as_posix()
            try:
                text = LOADERS[datei.suffix.lower()](datei)
            except Exception:
                logger.exception("Konnte %s nicht lesen – wird übersprungen", datei)
                continue
            for i, teil in enumerate(split_text(text, chunk_size, overlap)):
                chunks.append(
                    Chunk(
                        text=teil,
                        dokument=name,
                        titel=datei.stem,
                        gruppe=gruppe,
                        position=i,
                        pfad_absolut=str(datei.resolve()),
                    )
                )
        logger.info("Dokumente aus %s geladen", basis_pfad)
    logger.info("%d Chunks insgesamt", len(chunks))
    return chunks
