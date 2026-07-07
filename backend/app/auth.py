"""Benutzerverwaltung und Authentifizierung.

Prototyp: Benutzer liegen in einer YAML-Datei mit PBKDF2-Passwort-Hashes.
Produktiv wird dieser Baustein gegen LDAP / Active Directory / Keycloak (OIDC)
ausgetauscht – die restliche Anwendung kennt nur das `User`-Modell.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from pathlib import Path

import jwt
import yaml
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from .config import Settings, get_settings

PBKDF2_ITERATIONS = 200_000


class User(BaseModel):
    username: str
    anzeigename: str = ""
    rollen: list[str] = []
    gruppen: list[str] = []

    @property
    def ist_admin(self) -> bool:
        return "admin" in self.rollen

    def darf_gruppe(self, gruppe: str) -> bool:
        return "*" in self.gruppen or gruppe in self.gruppen


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return "pbkdf2$%s$%s" % (
        base64.b64encode(salt).decode(),
        base64.b64encode(digest).decode(),
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt_b64, digest_b64 = stored.split("$")
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
    except (ValueError, TypeError):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return hmac.compare_digest(actual, expected)


class UserStore:
    def __init__(self, users_file: Path):
        self._users_file = users_file
        self._users: dict[str, dict] = {}
        self.reload()

    def reload(self) -> None:
        if not self._users_file.exists():
            self._users = {}
            return
        raw = yaml.safe_load(self._users_file.read_text(encoding="utf-8")) or {}
        self._users = {u["username"]: u for u in raw.get("benutzer", [])}

    def authenticate(self, username: str, password: str) -> User | None:
        entry = self._users.get(username)
        if not entry or not verify_password(password, entry.get("password_hash", "")):
            return None
        return self.get(username)

    def get(self, username: str) -> User | None:
        entry = self._users.get(username)
        if not entry:
            return None
        return User(
            username=entry["username"],
            anzeigename=entry.get("anzeigename", entry["username"]),
            rollen=entry.get("rollen", []),
            gruppen=entry.get("gruppen", []),
        )


def create_token(user: User, settings: Settings) -> str:
    now = int(time.time())
    payload = {
        "sub": user.username,
        "iat": now,
        "exp": now + settings.jwt_ttl_minutes * 60,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


_bearer = HTTPBearer(auto_error=False)

# Wird in main.py beim App-Start gesetzt.
user_store: UserStore | None = None


def get_user_store() -> UserStore:
    assert user_store is not None, "UserStore wurde nicht initialisiert"
    return user_store


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
    store: UserStore = Depends(get_user_store),
) -> User:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Nicht angemeldet")
    try:
        payload = jwt.decode(credentials.credentials, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Ungültiges oder abgelaufenes Token")
    user = store.get(payload.get("sub", ""))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Benutzer existiert nicht mehr")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.ist_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Nur für Administratoren")
    return user
