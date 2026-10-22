from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.security import get_current_user, get_owned_request
from app.models.domain import LocalUser
from app.models.domain import Quote, Request
from app.schemas.proformas import QuoteValidationInput
from app.services.pdf_service import PDFService

router = APIRouter(tags=["Proformas"])


def serialize_quote(q):
    return {
        "id": q.id,
        "solicitud_id": q.request_id,
        "proveedor": q.provider.name if q.provider else None,
        "archivo": q.original_filename,
        "estado": q.status,
        "texto_recuperado": bool(q.raw_text_excerpt),
        "mensaje": None if q.raw_text_excerpt else "No fue posible extraer automáticamente la información necesaria.",
        "detalles": [{
            "id": d.id,
            "producto_servicio_id": d.product_service_id,
            "producto": d.product_service.name if d.product_service else None,
            "descripcion": d.description,
            "cantidad": d.quantity,
            "precio_unitario": d.unit_price,
            "precio_total": d.total_price,
            "caracteristicas": d.features_text,
            "confirmado": d.confirmed,
        } for d in q.details],
    }


@router.get("/solicitudes/{request_id}/proformas")
def list_quotes(request_id: int, db: Session = Depends(get_db), user: LocalUser = Depends(get_current_user)):
    get_owned_request(db, request_id, user)
    rows = db.scalars(
        select(Quote).where(Quote.request_id == request_id).order_by(Quote.created_at.desc(), Quote.id.desc())
    ).all()
    return [serialize_quote(q) for q in rows]


@router.get("/proformas/{quote_id}")
def get_quote(quote_id: int, db: Session = Depends(get_db), user: LocalUser = Depends(get_current_user)):
    q = db.get(Quote, quote_id)
    if not q:
        raise HTTPException(404, "Proforma no encontrada")
    get_owned_request(db, q.request_id, user)
    return serialize_quote(q)


@router.post("/solicitudes/{request_id}/proformas")
async def upload_quote(
    request_id: int,
    file: UploadFile = File(...),
    proveedor_id: int | None = Form(default=None),
    db: Session = Depends(get_db),
    user: LocalUser = Depends(get_current_user),
):
    get_owned_request(db, request_id, user)
    content = await file.read()
    try:
        q = PDFService(db).process_upload(request_id, proveedor_id, file.filename or "proforma.pdf", content)
        return serialize_quote(q)
    except Exception as exc:
        db.rollback()
        if isinstance(exc, ValueError):
            raise HTTPException(400, str(exc)) from exc
        raise HTTPException(422, "No fue posible procesar el PDF. Verifique que sea un PDF digital válido.") from exc


@router.put("/proformas/{quote_id}/validar")
def validate_quote(quote_id: int, payload: QuoteValidationInput, db: Session = Depends(get_db), user: LocalUser = Depends(get_current_user)):
    record = db.get(Quote, quote_id)
    if not record:
        raise HTTPException(404, "Proforma no encontrada")
    get_owned_request(db, record.request_id, user)
    try:
        q = PDFService(db).validate(quote_id, payload.proveedor_id, [d.model_dump() for d in payload.detalles])
        return serialize_quote(q)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
