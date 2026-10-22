"""Pruebas reproducibles de controles OE3, sin PostgreSQL ni SMTP externo."""
import os
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("SESSION_SECRET", "test-session-secret-only")

from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from fastapi import HTTPException

from app.db.base import Base
from app.models.domain import (LocalUser, Request, UserSmtpAccount)
from app.api.security import get_owned_request, require_admin
from app.services.nlp import NLPService
from app.services.email_service import EmailService


def setup_db():
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return engine


def test_owner_access_and_roles():
    engine = setup_db()
    with Session(engine) as db:
        a = LocalUser(username="a", display_name="A", password_hash="test", role="USUARIO_FINAL")
        b = LocalUser(username="b", display_name="B", password_hash="test", role="USUARIO_FINAL")
        admin = LocalUser(username="admin", display_name="Admin", password_hash="test", role="ADMIN_GLOBAL")
        db.add_all([a,b,admin]); db.flush()
        req = Request(original_text="2 laptops", owner_user_id=a.id)
        db.add(req); db.flush()
        assert get_owned_request(db,req.id,a).id == req.id
        try:
            get_owned_request(db,req.id,b)
            assert False, "No se bloqueó lectura cruzada"
        except HTTPException as exc:
            assert exc.status_code == 404
        try:
            require_admin(b)
            assert False, "No se bloqueó la operación administrativa"
        except HTTPException as exc:
            assert exc.status_code == 403
        assert require_admin(admin).id == admin.id


def test_regional_phrase_and_multi_item():
    service = NLPService(None)
    one = service.extract("Ocupo cinco compus portátiles Dell con 16 GB RAM")
    assert len(one) == 1
    assert one[0].product_name == "Laptop"
    assert one[0].quantity == 5
    assert one[0].brand_name == "Dell"
    two = service.extract("2 laptops y 3 monitores")
    assert len(two) == 2
    assert [i.quantity for i in two] == [2,3]


def test_smtp_key_encryption_roundtrip():
    key = Fernet.generate_key()
    secret = "clave-de-prueba-sintetica"
    cipher = Fernet(key).encrypt(secret.encode())
    assert cipher.decode() != secret
    assert Fernet(key).decrypt(cipher).decode() == secret
