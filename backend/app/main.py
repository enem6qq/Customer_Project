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


state = AppState()


def _reindex(settings: Settings) -> int:
    chunks = lade_dokumente(
        settings.tenant.dokumente_verzeichnis,
        chunk_size=settings.tenant.retrieval.chunk_size,
        overlap=settings.tenant.retrieval.chunk_overlap,
    )
    state.retriever.index(chunks)
    return len(chunks)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    auth.user_store = UserStore(settings.users_file)
    state.retriever = erstelle_retriever(settings.tenant.retrieval.provider)
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


class ChatRequest(BaseModel):
    frage: str


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
    antwort = state.llm.antworte(frage, treffer, settings.tenant.unternehmen.name)
    quellen = [
        Quelle(
            dokument=t.chunk.dokument,
            titel=t.chunk.titel,
            gruppe=t.chunk.gruppe,
            score=round(t.score, 3),
            auszug=(t.chunk.text[:300] + " …") if len(t.chunk.text) > 300 else t.chunk.text,
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
    chunks = state.retriever.anzahl_chunks if isinstance(state.retriever, BM25Retriever) else None
    return {
        "status": "ok",
        "unternehmen": settings.tenant.unternehmen.name,
        "llm_provider": settings.tenant.llm.provider,
        "chunks": chunks,
    }


# ---------------------------------------------------------------- Frontend

@app.get("/", include_in_schema=False)
def index():
    return FileResponse(FRONTEND_DIR / "index.html")


app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
