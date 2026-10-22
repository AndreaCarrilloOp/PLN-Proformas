"""Administración por usuario de SMTP cifrado (nunca devuelve la contraseña)."""
from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.security import get_current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models.domain import LocalUser, UserSmtpAccount

router = APIRouter(prefix="/smtp", tags=["Cuenta SMTP"])


class SMTPInput(BaseModel):
    host: str = Field(min_length=1, max_length=200)
    port: int = Field(ge=1, le=65535)
    username: str | None = Field(default=None, max_length=200)
    from_email: str = Field(min_length=3, max_length=200)
    password: str | None = Field(default=None, max_length=300)
    use_tls: bool = True


@router.get("/mi-cuenta")
def read_account(db: Session = Depends(get_db), user: LocalUser = Depends(get_current_user)):
    account = db.get(UserSmtpAccount, user.id)
    if account is None:
        return {"configurada": False}
    return {"configurada": True, "host": account.host, "port": account.port,
            "username": account.username, "from_email": account.from_email,
            "use_tls": account.use_tls, "tiene_clave": bool(account.password_encrypted)}


@router.put("/mi-cuenta")
def save_account(payload: SMTPInput, db: Session = Depends(get_db), user: LocalUser = Depends(get_current_user)):
    key = get_settings().smtp_fernet_key
    if not key:
        raise HTTPException(503, "SMTP_FERNET_KEY no configurada")
    try:
        fernet = Fernet(key.encode())
    except ValueError as exc:
        raise HTTPException(503, "Clave de cifrado SMTP inválida") from exc

    account = db.get(UserSmtpAccount, user.id)
    if account is None:
        account = UserSmtpAccount(user_id=user.id)
        db.add(account)
    account.host = payload.host.strip()
    account.port = payload.port
    account.username = payload.username.strip() if payload.username else None
    account.from_email = payload.from_email.strip()
    account.use_tls = payload.use_tls
    if payload.password is not None:
        account.password_encrypted = fernet.encrypt(payload.password.encode()).decode() if payload.password else None
    db.commit()
    return {"configurada": True, "mensaje": "Cuenta SMTP guardada de forma cifrada"}
