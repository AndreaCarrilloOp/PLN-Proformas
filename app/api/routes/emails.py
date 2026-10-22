from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.security import get_current_user, get_owned_request, ensure_provider_request, ensure_email
from app.models.domain import LocalUser
from app.models.domain import EmailSend, ProviderRequest
from app.schemas.emails import EmailUpdate
from app.services.email_service import EmailService

router = APIRouter(tags=["Correos"])


def _serialize(email: EmailSend, provider_name: str | None = None) -> dict:
    return {
        "id": email.id,
        "solicitud_proveedor_id": email.provider_request_id,
        "proveedor": provider_name,
        "destinatario": email.to_email,
        "asunto": email.subject,
        "contenido": email.body_text,
        "estado": email.status,
        "enviado_en": email.sent_at,
        "error": email.error_message,
    }


@router.post("/solicitudes-proveedor/{provider_request_id}/correo/borrador")
def draft_email(provider_request_id: int, db: Session = Depends(get_db), user: LocalUser = Depends(get_current_user)):
    ensure_provider_request(db, provider_request_id, user)
    try:
        email = EmailService(db).draft(provider_request_id)
        provider_request = db.get(ProviderRequest, provider_request_id)
        return _serialize(email, provider_request.provider.name if provider_request else None)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/solicitudes/{request_id}/correos")
def list_request_emails(request_id: int, db: Session = Depends(get_db), user: LocalUser = Depends(get_current_user)):
    get_owned_request(db, request_id, user)
    rows = db.execute(
        select(EmailSend, ProviderRequest)
        .join(ProviderRequest, ProviderRequest.id == EmailSend.provider_request_id)
        .where(ProviderRequest.request_id == request_id)
        .order_by(EmailSend.id)
    ).all()
    return [_serialize(email, provider_request.provider.name) for email, provider_request in rows]


@router.put("/correos/{email_id}")
def update_email(email_id: int, payload: EmailUpdate, db: Session = Depends(get_db), user: LocalUser = Depends(get_current_user)):
    ensure_email(db, email_id, user)
    try:
        email = EmailService(db).update(
            email_id,
            to_email=payload.destinatario,
            subject=payload.asunto,
            body_text=payload.contenido,
        )
        provider_request = db.get(ProviderRequest, email.provider_request_id)
        return _serialize(email, provider_request.provider.name if provider_request else None)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/correos/{email_id}/autorizar")
def authorize_email(email_id: int, db: Session = Depends(get_db), user: LocalUser = Depends(get_current_user)):
    ensure_email(db, email_id, user)
    try:
        email = EmailService(db).decide(email_id, authorized=True)
        provider_request = db.get(ProviderRequest, email.provider_request_id)
        return _serialize(email, provider_request.provider.name if provider_request else None)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/correos/{email_id}/rechazar")
def reject_email(email_id: int, db: Session = Depends(get_db), user: LocalUser = Depends(get_current_user)):
    ensure_email(db, email_id, user)
    try:
        email = EmailService(db).decide(email_id, authorized=False)
        provider_request = db.get(ProviderRequest, email.provider_request_id)
        return _serialize(email, provider_request.provider.name if provider_request else None)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/correos/{email_id}/enviar")
def send_email(email_id: int, db: Session = Depends(get_db), user: LocalUser = Depends(get_current_user)):
    ensure_email(db, email_id, user)
    try:
        email = EmailService(db).send(email_id)
        provider_request = db.get(ProviderRequest, email.provider_request_id)
        return _serialize(email, provider_request.provider.name if provider_request else None)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
