from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.security import get_current_user, get_owned_request
from app.models.domain import LocalUser
from app.models.domain import ProviderRequest
from app.services.providers import ProviderService

router = APIRouter(tags=["Proveedores"])


@router.post("/solicitudes/{request_id}/proveedores")
def generate_provider_requests(request_id: int, db: Session = Depends(get_db), user: LocalUser = Depends(get_current_user)):
    get_owned_request(db, request_id, user)
    service = ProviderService(db)
    try:
        return service.serialize(service.generate_for_request(request_id))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/solicitudes/{request_id}/proveedores")
def list_provider_requests(request_id: int, db: Session = Depends(get_db), user: LocalUser = Depends(get_current_user)):
    get_owned_request(db, request_id, user)
    prs = db.scalars(select(ProviderRequest).where(ProviderRequest.request_id == request_id)).all()
    return ProviderService(db).serialize(prs)
