"""Dependencias de acceso: rechazar lectura o escritura entre usuarios."""
from fastapi import Depends, HTTPException, Request as HttpRequest
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.domain import EmailSend, LocalUser, ProviderRequest, Request


def get_current_user(request: HttpRequest) -> LocalUser:
    user = getattr(request.state, "user", None)
    if user is None or not user.active:
        raise HTTPException(401, "Autenticación requerida")
    return user


def require_admin(user: LocalUser = Depends(get_current_user)) -> LocalUser:
    if user.role != "ADMIN_GLOBAL":
        raise HTTPException(403, "Esta operación requiere el rol de administrador global")
    return user


def get_owned_request(db: Session, request_id: int, user: LocalUser) -> Request:
    record = db.get(Request, request_id)
    if record is None or record.owner_user_id != user.id:
        raise HTTPException(404, "Solicitud no encontrada")
    return record


def ensure_provider_request(db: Session, provider_request_id: int, user: LocalUser) -> ProviderRequest:
    record = db.get(ProviderRequest, provider_request_id)
    if record is None:
        raise HTTPException(404, "Solicitud por proveedor no encontrada")
    get_owned_request(db, record.request_id, user)
    return record


def ensure_email(db: Session, email_id: int, user: LocalUser) -> EmailSend:
    record = db.get(EmailSend, email_id)
    if record is None:
        raise HTTPException(404, "Correo no encontrado")
    ensure_provider_request(db, record.provider_request_id, user)
    return record
