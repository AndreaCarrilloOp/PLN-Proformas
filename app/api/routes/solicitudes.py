from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.security import get_current_user, get_owned_request
from app.models.domain import LocalUser
from app.models.domain import EmailSend, Provider, ProviderRequest, Quote, Request
from app.schemas.solicitudes import AnswerCreate, ConfirmationCreate, RequestCreate
from app.services.requests import RequestService
from app.services.serialization import request_to_dict

router = APIRouter(prefix="/solicitudes", tags=["Solicitudes"])


@router.post("")
def create_request(payload: RequestCreate, db: Session = Depends(get_db), user: LocalUser = Depends(get_current_user)):
    return request_to_dict(RequestService(db).create(payload.texto, user.id))


@router.get("/buscar")
def search_requests(
    q: str = Query(default="", max_length=200),
    db: Session = Depends(get_db),
    user: LocalUser = Depends(get_current_user),
):
    """Busca solicitudes por ID, texto original o correo/asunto asociado.

    La búsqueda existe para recuperar una solicitud previa desde pantallas como
    Proformas PDF sin introducir lectura automática del buzón de correo.
    """
    term = q.strip()
    stmt = select(Request).where(Request.owner_user_id == user.id).order_by(Request.created_at.desc()).limit(25)

    if term:
        pattern = f"%{term}%"
        filters = [Request.original_text.ilike(pattern)]
        if term.isdigit():
            filters.append(Request.id == int(term))

        requests_by_email = (
            select(ProviderRequest.request_id)
            .join(Provider, Provider.id == ProviderRequest.provider_id)
            .outerjoin(EmailSend, EmailSend.provider_request_id == ProviderRequest.id)
            .where(
                or_(
                    Provider.email.ilike(pattern),
                    EmailSend.to_email.ilike(pattern),
                    EmailSend.subject.ilike(pattern),
                )
            )
        )
        filters.append(Request.id.in_(requests_by_email))
        stmt = stmt.where(or_(*filters))

    requests = db.scalars(stmt).all()
    result = []
    for req in requests:
        provider_rows = db.scalars(
            select(Provider)
            .join(ProviderRequest, ProviderRequest.provider_id == Provider.id)
            .where(ProviderRequest.request_id == req.id)
        ).all()
        email_rows = db.scalars(
            select(EmailSend)
            .join(ProviderRequest, ProviderRequest.id == EmailSend.provider_request_id)
            .where(ProviderRequest.request_id == req.id)
            .order_by(EmailSend.id.desc())
        ).all()
        quote_count = db.scalar(select(func.count(Quote.id)).where(Quote.request_id == req.id)) or 0

        emails = []
        seen_emails = set()
        for email in [p.email for p in provider_rows] + [e.to_email for e in email_rows]:
            if email and email not in seen_emails:
                seen_emails.add(email)
                emails.append(email)

        providers = []
        seen_providers = set()
        for provider in provider_rows:
            if provider.name not in seen_providers:
                seen_providers.add(provider.name)
                providers.append(provider.name)

        result.append({
            "id": req.id,
            "texto_original": req.original_text,
            "estado": req.status,
            "creada_en": req.created_at,
            "proveedores": providers,
            "correos": emails,
            "proformas": quote_count,
        })
    return result


@router.get("/{request_id}")
def get_request(request_id: int, db: Session = Depends(get_db), user: LocalUser = Depends(get_current_user)):
    req = get_owned_request(db, request_id, user)
    return request_to_dict(req)


@router.post("/{request_id}/respuestas")
def answer_question(request_id: int, payload: AnswerCreate, db: Session = Depends(get_db), user: LocalUser = Depends(get_current_user)):
    get_owned_request(db, request_id, user)
    try:
        req = RequestService(db).answer(request_id, payload.pregunta_id, payload.respuesta)
        return request_to_dict(req)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/{request_id}/confirmaciones")
def confirm_interpretation(request_id: int, payload: ConfirmationCreate, db: Session = Depends(get_db), user: LocalUser = Depends(get_current_user)):
    get_owned_request(db, request_id, user)
    try:
        req = RequestService(db).confirm(request_id, payload.transformacion_id, payload.confirmado, payload.valor_corregido)
        return request_to_dict(req)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
