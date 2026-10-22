from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.domain import LocalUser

PBKDF2_ITERATIONS = 390_000


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def hash_password(password: str, *, salt: bytes | None = None, iterations: int = PBKDF2_ITERATIONS) -> str:
    if not password:
        raise ValueError("La contraseña no puede estar vacía")
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${_b64encode(salt)}${_b64encode(digest)}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations_raw, salt_raw, digest_raw = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_raw)
        salt = _b64decode(salt_raw)
        expected = _b64decode(digest_raw)
    except (ValueError, TypeError):
        return False

    candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(candidate, expected)


def authenticate_user(db: Session, username: str, password: str) -> LocalUser | None:
    normalized = username.strip().lower()
    user = db.scalar(select(LocalUser).where(LocalUser.username == normalized))
    if not user or not user.active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


@dataclass(frozen=True)
class SessionIdentity:
    user_id: int
    username: str
    expires_at: int


def create_session_token(user: LocalUser, secret: str, ttl_minutes: int) -> str:
    payload = {
        "uid": user.id,
        "usr": user.username,
        "exp": int(time.time()) + (ttl_minutes * 60),
    }
    body = _b64encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signature = _b64encode(hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest())
    return f"{body}.{signature}"


def parse_session_token(token: str | None, secret: str) -> SessionIdentity | None:
    if not token:
        return None
    try:
        body, signature = token.split(".", 1)
        expected = _b64encode(hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            return None
        payload = json.loads(_b64decode(body).decode("utf-8"))
        expires_at = int(payload["exp"])
        if expires_at < int(time.time()):
            return None
        return SessionIdentity(
            user_id=int(payload["uid"]),
            username=str(payload["usr"]),
            expires_at=expires_at,
        )
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None
