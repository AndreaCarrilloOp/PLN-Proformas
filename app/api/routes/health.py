from fastapi import APIRouter, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.db.session import engine

router = APIRouter(tags=["Salud"])
settings = get_settings()


@router.get("/health")
def health():
    return {
        "status": "ok",
        "service": "pln-proformas",
        "version": settings.app_version,
    }


@router.get("/health/ready")
def readiness():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Base de datos no disponible") from exc
    return {"status": "ready", "database": "ok"}
