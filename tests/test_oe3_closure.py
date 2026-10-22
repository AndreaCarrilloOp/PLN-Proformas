"""Cierre OE3: pruebas negativas, unidades y persistencia controlada."""
import os
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.db.base import Base
from app.db.seed import seed_database
from app.models.domain import LocalUser, Request, RequestItem, UnitMeasure
from app.services.nlp import NLPService
from app.services.requests import RequestService
from app.services.auth import hash_password

@pytest.fixture
def db():
    engine=create_engine("sqlite+pysqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        seed_database(db)
        yield db
    engine.dispose()

def test_noncommercial_rejected_without_record(db):
    user=LocalUser(username="negativo",display_name="Test",password_hash="x")
    db.add(user);db.commit()
    start=db.query(Request).count()
    with pytest.raises(ValueError,match="no describe una solicitud comercial"):
        RequestService(db).create("Ocupo el puesto de administrador",user.id)
    assert db.query(Request).count()==start

def test_unknown_commercial_input_asks_for_clarification(db):
    user=LocalUser(username="desconocido",display_name="Test",password_hash="x")
    db.add(user);db.commit()
    record=RequestService(db).create("Necesito 5 escritorios de oficina",user.id)
    assert record.status!="COMPLETO"
    assert any(q.field_key=="producto" for item in record.items for q in item.questions)

@pytest.mark.parametrize("message,quantity,unit",[
    ("Necesito 3 cajas de lapiceros negros",3,"caja"),
    ("Necesito 4 resmas de papel tamaño carta",4,"resma"),
    ("Necesito 5 paquetes de papel",5,"paquete"),
    ("Necesito 6 monitores",6,"unidad"),
    ("Requiero un servicio de mantenimiento",1,"servicio"),
])
def test_units_extract(message,quantity,unit):
    result=NLPService(None).extract(message)
    assert len(result)==1
    assert result[0].quantity==quantity
    assert result[0].unit_symbol==unit

def test_unit_persisted_separately_by_item(db):
    user=LocalUser(username="unidades",display_name="Test",password_hash="x")
    db.add(user);db.commit()
    req=RequestService(db).create("Necesito 3 cajas de lapiceros y 4 resmas de papel",user.id)
    items=db.scalars(select(RequestItem).where(RequestItem.request_id==req.id).order_by(RequestItem.id)).all()
    assert len(items)==2
    assert [float(x.quantity) for x in items]==[3,4]
    assert [x.unit_measure.symbol for x in items]==["caja","resma"]
    assert [x.unit_measure.name for x in items]==["Caja","Resma"]
