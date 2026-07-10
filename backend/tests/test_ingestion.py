import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ingestion import lade_dokumente, split_text


def test_split_text_respektiert_chunkgroesse():
    text = "\n\n".join(f"Absatz {i} " + "x" * 120 for i in range(10))
    chunks = split_text(text, chunk_size=300, overlap=50)
    assert len(chunks) > 1
    assert all(len(c) <= 300 for c in chunks)


def test_split_text_teilt_lange_absaetze():
    chunks = split_text("y" * 2000, chunk_size=500, overlap=100)
    assert all(len(c) <= 500 for c in chunks)
    assert sum(len(c) for c in chunks) >= 2000  # nichts geht verloren


def test_gruppe_aus_ordnername(tmp_path):
    (tmp_path / "personal").mkdir()
    (tmp_path / "personal" / "a.md").write_text("Inhalt Personal", encoding="utf-8")
    (tmp_path / "b.md").write_text("Inhalt Wurzel", encoding="utf-8")
    chunks = lade_dokumente(tmp_path)
    gruppen = {c.dokument: c.gruppe for c in chunks}
    assert gruppen["personal/a.md"] == "personal"
    assert gruppen["b.md"] == "allgemein"
    # Absoluter Pfad zur Originaldatei wird mitgeführt (Quellen-Klick)
    assert all(Path(c.pfad_absolut).is_file() for c in chunks)


def test_mehrere_ablageorte(tmp_path):
    """Mehrere Ordner werden gemeinsam indiziert; Namen bleiben eindeutig."""
    ablage_a = tmp_path / "Projekte"
    ablage_b = tmp_path / "Vertraege"
    ablage_a.mkdir()
    ablage_b.mkdir()
    (ablage_a / "notiz.md").write_text("Projektnotiz", encoding="utf-8")
    (ablage_b / "notiz.md").write_text("Vertragsnotiz", encoding="utf-8")
    chunks = lade_dokumente([ablage_a, ablage_b])
    namen = sorted(c.dokument for c in chunks)
    assert namen == ["Projekte/notiz.md", "Vertraege/notiz.md"]
