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


def test_multiattribute_answer_clears_both_questions():
    from app.models.domain import (Characteristic, ProductService, RequirementTemplate,
                                   TemplateField, RequestItem, ValidationQuestion, Category)
    from app.services.requests import RequestService
    engine = setup_db()
    with Session(engine) as db:
        category = Category(name="Portátiles")
        product = ProductService(name="Laptop", category=category, kind="PRODUCTO")
        ram = Characteristic(key="ram", name="RAM")
        disk = Characteristic(key="almacenamiento", name="Almacenamiento")
        db.add_all([product, ram, disk]); db.flush()
        template = RequirementTemplate(product_service_id=product.id, name="Requisitos", active=True)
        db.add(template); db.flush()
        db.add_all([
            TemplateField(template_id=template.id, characteristic_id=ram.id,
                          question_text="¿RAM?", required=True),
            TemplateField(template_id=template.id, characteristic_id=disk.id,
                          question_text="¿Almacenamiento?", required=True)
        ])
        user = LocalUser(username="testmulti", display_name="Test", password_hash="x")
        db.add(user); db.flush()
        req = Request(original_text="1 laptop", owner_user_id=user.id)
        db.add(req); db.flush()
        item = RequestItem(request_id=req.id, product_service_id=product.id,
                           original_fragment="1 laptop", quantity=1)
        db.add(item); db.flush()
        first = ValidationQuestion(request_item_id=item.id, field_key="ram",
                                   question_text="¿RAM?", status="PENDIENTE")
        second = ValidationQuestion(request_item_id=item.id, field_key="almacenamiento",
                                    question_text="¿Almacenamiento?", status="PENDIENTE")
        db.add_all([first, second]); db.flush()
        req_id, first_id = req.id, first.id
        db.commit()
        result = RequestService(db).answer(req_id, first_id, "16 GB RAM y 512 GB SSD")
        final_item = result.items[0]
        values = {c.characteristic.key: c.normalized_value for c in final_item.characteristics}
        assert values == {"ram": "16 GB", "almacenamiento": "512 GB SSD"}
        assert all(q.status == "RESPONDIDA" for q in final_item.questions)
        assert result.status == "COMPLETO"
