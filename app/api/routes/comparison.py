from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.security import get_current_user, get_owned_request
from app.models.domain import LocalUser
from app.services.comparison import comparison_for_request

router = APIRouter(tags=["Comparación"])


@router.get("/solicitudes/{request_id}/comparacion")
def comparison(request_id: int, db: Session = Depends(get_db), user: LocalUser = Depends(get_current_user)):
    get_owned_request(db, request_id, user)
    return comparison_for_request(db, request_id)
