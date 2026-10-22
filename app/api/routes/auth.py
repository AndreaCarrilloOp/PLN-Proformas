from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models.domain import LocalUser
from app.services.auth import authenticate_user, create_session_token, parse_session_token

router = APIRouter(prefix="/auth", tags=["Autenticación"])
settings = get_settings()


class LoginInput(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


def serialize_user(user: LocalUser) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "nombre": user.display_name,
    }


@router.post("/login")
def login(payload: LoginInput, response: Response, db: Session = Depends(get_db)):
    user = authenticate_user(db, payload.username, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos")

    token = create_session_token(user, settings.session_secret, settings.session_ttl_minutes)
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_ttl_minutes * 60,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )
    return {"usuario": serialize_user(user)}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        secure=settings.session_cookie_secure,
        samesite="lax",
    )
    return {"ok": True}


@router.get("/me")
def me(request: Request, db: Session = Depends(get_db)):
    identity = parse_session_token(request.cookies.get(settings.session_cookie_name), settings.session_secret)
    if not identity:
        raise HTTPException(status_code=401, detail="Sesión no válida")
    user = db.get(LocalUser, identity.user_id)
    if not user or not user.active:
        raise HTTPException(status_code=401, detail="Sesión no válida")
    return {"usuario": serialize_user(user)}
