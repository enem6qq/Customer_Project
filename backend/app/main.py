"""FastAPI-Anwendung: verbindet Auth, Ingestion, Retrieval und LLM."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import auth
from .auth import User, UserStore, create_token, get_current_user, require_admin
from .config import REPO_ROOT, Settings, get_settings
from .ingestion import lade_dokumente
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
    yield


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
    quellen = [
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
    return ChatResponse(
        antwort=antwort,
        quellen=quellen,
        ansprechpartner=_passende_ansprechpartner(frage, settings),
    )


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
    }


# ---------------------------------------------------------------- Frontend

@app.get("/", include_in_schema=False)
def index():
    return FileResponse(FRONTEND_DIR / "index.html")


app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
