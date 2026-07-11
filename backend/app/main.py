"""FastAPI-Anwendung: verbindet Auth, Ingestion, Retrieval und LLM."""

from __future__ import annotations

import asyncio
import json
import logging
from collections import Counter
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import auth
from .auth import User, UserStore, create_token, get_current_user, require_admin
from .config import REPO_ROOT, Settings, get_settings
from .ingestion import LOADERS, lade_dokumente
from .llm import LLMProvider, erstelle_llm
from .retrieval import BM25Retriever, Retriever, erstelle_retriever

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

FRONTEND_DIR = REPO_ROOT / "frontend"


class AppState:
    retriever: Retriever
    llm: LLMProvider
    # Anzeigename -> (absoluter Pfad, Zugriffsgruppe). Nur hierüber sind
    # Dateien abrufbar – kein direkter Dateisystemzugriff über die API,
    # dadurch weder Path-Traversal möglich noch Zugriff an RBAC vorbei.
    dokumente: dict[str, tuple[str, str]] = {}


state = AppState()


def _reindex(settings: Settings) -> int:
    chunks = lade_dokumente(
        settings.tenant.dokumente_verzeichnisse,
        chunk_size=settings.tenant.retrieval.chunk_size,
        overlap=settings.tenant.retrieval.chunk_overlap,
    )
    state.retriever.index(chunks)
    state.dokumente = {c.dokument: (c.pfad_absolut, c.gruppe) for c in chunks}
    return len(chunks)


def _dokumente_signatur(verzeichnisse: list[Path]) -> tuple:
    """Fingerabdruck aller Dokumentdateien (Pfad, Änderungszeit, Größe).

    Ändert er sich, wurde etwas hinzugefügt, geändert oder gelöscht –
    dann indiziert der Wächter automatisch neu.
    """
    eintraege = []
    for basis in verzeichnisse:
        if not basis.exists():
            continue
        for datei in basis.rglob("*"):
            if datei.is_file() and datei.suffix.lower() in LOADERS:
                st = datei.stat()
                eintraege.append((str(datei), st.st_mtime_ns, st.st_size))
    return tuple(sorted(eintraege))


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    auth.user_store = UserStore(settings.users_file)
    try:
        state.retriever = erstelle_retriever(settings.tenant.retrieval)
    except Exception:
        # Z. B. Embedding-Pakete fehlen oder Modell-Download nicht möglich:
        # lieber mit Volltextsuche starten als gar nicht.
        logger.exception(
            "Retrieval-Provider %r konnte nicht initialisiert werden – "
            "falle auf BM25 (Volltextsuche) zurück",
            settings.tenant.retrieval.provider,
        )
        state.retriever = BM25Retriever()
    state.llm = erstelle_llm(settings.tenant.llm)
    anzahl = _reindex(settings)
    logger.info(
        "Gestartet für '%s' – %d Chunks indiziert, LLM-Provider: %s",
        settings.tenant.unternehmen.name,
        anzahl,
        settings.tenant.llm.provider,
    )

    stop = asyncio.Event()

    async def waechter() -> None:
        intervall = settings.tenant.auto_reindex_sekunden
        verzeichnisse = settings.tenant.dokumente_verzeichnisse
        signatur = await asyncio.to_thread(_dokumente_signatur, verzeichnisse)
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), timeout=intervall)
                return  # stop gesetzt -> sauber beenden
            except asyncio.TimeoutError:
                pass
            neue_signatur = await asyncio.to_thread(_dokumente_signatur, verzeichnisse)
            if neue_signatur != signatur:
                signatur = neue_signatur
                neu = await asyncio.to_thread(_reindex, settings)
                logger.info("Ablage geändert – automatisch neu indiziert: %d Chunks", neu)

    task = None
    if settings.tenant.auto_reindex_sekunden > 0:
        task = asyncio.create_task(waechter())

    yield

    stop.set()
    if task is not None:
        await task


app = FastAPI(title="Wissens-Chatbot", lifespan=lifespan)


# ---------------------------------------------------------------- Auth

class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    username: str
    anzeigename: str
    rollen: list[str]
    gruppen: list[str]


@app.post("/api/auth/login", response_model=LoginResponse)
def login(body: LoginRequest, settings: Settings = Depends(get_settings)):
    store = auth.get_user_store()
    user = store.authenticate(body.username, body.password)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Benutzername oder Passwort falsch")
    return LoginResponse(
        token=create_token(user, settings),
        username=user.username,
        anzeigename=user.anzeigename,
        rollen=user.rollen,
        gruppen=user.gruppen,
    )


@app.get("/api/auth/me")
def me(user: User = Depends(get_current_user)):
    return user


# ---------------------------------------------------------------- Chat & Suche

class Quelle(BaseModel):
    dokument: str
    titel: str
    gruppe: str
    score: float
    auszug: str
    pfad: str


class VerlaufNachricht(BaseModel):
    rolle: str  # "nutzer" oder "bot"
    text: str


class ChatRequest(BaseModel):
    frage: str
    verlauf: list[VerlaufNachricht] = []


class ChatResponse(BaseModel):
    antwort: str
    quellen: list[Quelle]
    ansprechpartner: list[dict]


def _passende_ansprechpartner(frage: str, settings: Settings) -> list[dict]:
    """Sehr einfache Zuordnung: Bereichsname kommt in der Frage vor."""
    frage_klein = frage.lower()
    return [
        a.model_dump()
        for a in settings.tenant.ansprechpartner
        if a.bereich.lower() in frage_klein
    ]


def _baue_quellen(treffer) -> list[Quelle]:
    return [
        Quelle(
            dokument=t.chunk.dokument,
            titel=t.chunk.titel,
            gruppe=t.chunk.gruppe,
            score=round(t.score, 3),
            auszug=(t.chunk.text[:300] + " …") if len(t.chunk.text) > 300 else t.chunk.text,
            pfad=t.chunk.pfad_absolut,
        )
        for t in treffer
    ]


@app.post("/api/chat", response_model=ChatResponse)
def chat(
    body: ChatRequest,
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    frage = body.frage.strip()
    if not frage:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Frage darf nicht leer sein")
    treffer = state.retriever.suche(frage, user, top_k=settings.tenant.retrieval.top_k)
    # Nur die letzten Nachrichten mitgeben – hält den Prompt klein.
    verlauf = [v.model_dump() for v in body.verlauf[-6:]]
    antwort = state.llm.antworte(frage, treffer, settings.tenant.unternehmen.name, verlauf)
    return ChatResponse(
        antwort=antwort,
        quellen=_baue_quellen(treffer),
        ansprechpartner=_passende_ansprechpartner(frage, settings),
    )


@app.post("/api/chat/stream")
def chat_stream(
    body: ChatRequest,
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    """Wie /api/chat, aber als NDJSON-Stream: erst ein meta-Ereignis mit
    Quellen und Ansprechpartnern (die stehen sofort fest), dann die Antwort
    stückweise als token-Ereignisse, abschließend ende.

    Die Rechteprüfung passiert wie immer VOR der LLM-Anfrage im Retrieval.
    """
    frage = body.frage.strip()
    if not frage:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Frage darf nicht leer sein")
    treffer = state.retriever.suche(frage, user, top_k=settings.tenant.retrieval.top_k)
    verlauf = [v.model_dump() for v in body.verlauf[-6:]]
    unternehmen = settings.tenant.unternehmen.name
    meta = {
        "typ": "meta",
        "quellen": [q.model_dump() for q in _baue_quellen(treffer)],
        "ansprechpartner": _passende_ansprechpartner(frage, settings),
    }

    def generator():
        yield json.dumps(meta, ensure_ascii=False) + "\n"
        try:
            for stueck in state.llm.antworte_stream(frage, treffer, unternehmen, verlauf):
                yield json.dumps({"typ": "token", "text": stueck}, ensure_ascii=False) + "\n"
        except Exception:
            logger.exception("Fehler beim Streamen der Antwort")
            yield json.dumps(
                {"typ": "token", "text": "Es ist ein Fehler bei der Antworterzeugung aufgetreten."},
                ensure_ascii=False,
            ) + "\n"
        yield json.dumps({"typ": "ende"}) + "\n"

    return StreamingResponse(generator(), media_type="application/x-ndjson")


@app.get("/api/documents/search")
def dokumentsuche(
    q: str,
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    treffer = state.retriever.suche(q, user, top_k=settings.tenant.retrieval.top_k)
    return {
        "treffer": [
            {
                "dokument": t.chunk.dokument,
                "titel": t.chunk.titel,
                "gruppe": t.chunk.gruppe,
                "score": round(t.score, 3),
                "auszug": t.chunk.text[:300],
            }
            for t in treffer
        ]
    }


@app.get("/api/documents/file")
def dokument_datei(
    name: str,
    user: User = Depends(get_current_user),
):
    """Liefert die Originaldatei eines indizierten Dokuments (Quellen-Klick).

    Abrufbar sind ausschließlich indizierte Dokumente über ihren Anzeigenamen –
    und nur, wenn der Benutzer die Zugriffsgruppe des Dokuments sehen darf.
    """
    eintrag = state.dokumente.get(name)
    if eintrag is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dokument nicht im Index")
    pfad, gruppe = eintrag
    if not user.darf_gruppe(gruppe):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Kein Zugriff auf dieses Dokument")
    datei = Path(pfad)
    if not datei.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Datei existiert nicht mehr")
    return FileResponse(datei, filename=datei.name, content_disposition_type="inline")


# ---------------------------------------------------------------- Feedback

class FeedbackRequest(BaseModel):
    frage: str
    antwort: str
    bewertung: str  # "gut" oder "schlecht"


@app.post("/api/feedback")
def feedback(
    body: FeedbackRequest,
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    """Speichert Nutzer-Feedback zu einer Antwort (👍/👎) als JSON-Zeile.

    Damit lässt sich messen, wo die Wissensbasis Lücken hat.
    """
    if body.bewertung not in ("gut", "schlecht"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "bewertung: gut|schlecht")
    eintrag = {
        "zeit": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "benutzer": user.username,
        "bewertung": body.bewertung,
        "frage": body.frage[:1000],
        "antwort": body.antwort[:1000],
    }
    datei = settings.feedback_datei
    datei.parent.mkdir(parents=True, exist_ok=True)
    with datei.open("a", encoding="utf-8") as f:
        f.write(json.dumps(eintrag, ensure_ascii=False) + "\n")
    return {"status": "ok"}


@app.get("/api/admin/feedback")
def feedback_liste(
    _admin: User = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    datei = settings.feedback_datei
    if not datei.exists():
        return {"eintraege": []}
    eintraege = []
    for zeile in datei.read_text(encoding="utf-8").splitlines():
        try:
            eintraege.append(json.loads(zeile))
        except json.JSONDecodeError:
            continue
    return {"eintraege": eintraege}


# ---------------------------------------------------------------- Admin & Status

@app.post("/api/admin/reindex")
def reindex(
    _admin: User = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    anzahl = _reindex(settings)
    return {"status": "ok", "chunks": anzahl}


@app.get("/api/health")
def health(settings: Settings = Depends(get_settings)):
    return {
        "status": "ok",
        "unternehmen": settings.tenant.unternehmen.name,
        "modus": settings.tenant.modus,
        "llm_provider": settings.tenant.llm.provider,
        "retrieval_provider": settings.tenant.retrieval.provider,
        "chunks": getattr(state.retriever, "anzahl_chunks", None),
        "beispiel_fragen": settings.tenant.beispiel_fragen,
    }


@app.get("/api/admin/stats")
def admin_stats(
    _admin: User = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    """Übersicht für das Admin-Dashboard."""
    gruppen = Counter(gruppe for _, gruppe in state.dokumente.values())
    feedback_zaehler = Counter()
    if settings.feedback_datei.exists():
        for zeile in settings.feedback_datei.read_text(encoding="utf-8").splitlines():
            try:
                feedback_zaehler[json.loads(zeile).get("bewertung", "?")] += 1
            except json.JSONDecodeError:
                continue
    return {
        "unternehmen": settings.tenant.unternehmen.name,
        "modus": settings.tenant.modus,
        "llm_provider": settings.tenant.llm.provider,
        "retrieval_provider": settings.tenant.retrieval.provider,
        "auto_reindex_sekunden": settings.tenant.auto_reindex_sekunden,
        "dokumente": len(state.dokumente),
        "chunks": getattr(state.retriever, "anzahl_chunks", None),
        "gruppen": dict(gruppen),
        "ablageorte": [str(p) for p in settings.tenant.dokumente_verzeichnisse],
        "feedback": {
            "gut": feedback_zaehler.get("gut", 0),
            "schlecht": feedback_zaehler.get("schlecht", 0),
        },
    }


# ---------------------------------------------------------------- Frontend

@app.get("/", include_in_schema=False)
def index():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/admin", include_in_schema=False)
def admin_seite():
    return FileResponse(FRONTEND_DIR / "admin.html")


app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
