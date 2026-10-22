"""OE3 / Tabla C1 del Capítulo III: S01-S16 sin alterar sus entradas."""
import os
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.domain import (ProductService, Category, LexicalVariant,
                               Brand, Request, LocalUser, Characteristic,
                               RequirementTemplate, TemplateField)
from app.services.nlp import NLPService
from app.services.requests import RequestService

CASES = [
    ("S01", "Necesito 3 resmas de papel tamaño carta.", ["Papel"], [3], {"tamano_papel": "carta"}),
    ("S02", "Cotizar 2 sillas de oficina ergonómicas.", ["Silla"], [2], {"ergonomia": "ergonómica"}),
    ("S03", "Solicito 5 cajas de lapiceros negros.", ["Lapicero"], [5], {"color": "negro"}),
    ("S04", "Requiero un servicio de mantenimiento de aire acondicionado.", ["Mantenimiento AC"], [1], {}),
    ("S05", "Ocupo 2 laptops Dell de 16 GB RAM y 4 monitores Samsung de 24 pulgadas.", ["Laptop", "Monitor"], [2, 4], {}),
    ("S06", "Cotizar 3 mesas plegables y 6 sillas apilables.", ["Mesa", "Silla"], [3, 6], {}),
    ("S07", "Necesito 10 cajas de sobres blancos y 8 cajas de carpetas azules.", ["Sobre", "Carpeta"], [10, 8], {}),
    ("S08", "Solicito 2 impresoras láser y 5 paquetes de papel fotográfico.", ["Impresora", "Papel fotográfico"], [2, 5], {}),
    ("S09", "Ocupo una compu portátil de 16 GB de RAM.", ["Laptop"], [1], {}),
    ("S10", "Necesito 3 compus de escritorio.", ["Desktop"], [3], {}),
    ("S11", "Ocupo 4 lapiceros azules y 2 marcadores permanentes.", ["Lapicero", "Marcador"], [4, 2], {}),
    ("S12", "Quisiera 2 notebooks con 8 GB de RAM.", ["Laptop"], [2], {}),
    ("S13", "Necesito varias sillas para recepción.", ["Silla"], [None], {}),
    ("S14", "Cotizar 3 cables HDMI.", ["Cable HDMI"], [3], {}),
    ("S15", "Ocupo 2 compus.", [None], [2], {}),
    ("S16", "Solicito 1 impresora compatible con mi equipo.", ["Impresora"], [1], {}),
]

CATALOG = {
    "Papel": ["papel", "resmas de papel"],
    "Silla": ["sillas", "sillas de oficina", "sillas apilables", "sillas ergonómicas de oficina"],
    "Lapicero": ["lapiceros"],
    "Mantenimiento AC": ["servicio de mantenimiento de aire acondicionado"],
    "Laptop": ["laptop", "laptops", "compu portátil", "notebooks"],
    "Desktop": ["compus de escritorio", "compu de escritorio"],
    "Monitor": ["monitor", "monitores"],
    "Mesa": ["mesas plegables"],
    "Sobre": ["sobres"],
    "Carpeta": ["carpetas"],
    "Impresora": ["impresora", "impresoras", "impresoras láser"],
    "Papel fotográfico": ["papel fotográfico"],
    "Marcador": ["marcadores", "marcadores permanentes"],
    "Cable HDMI": ["cables HDMI"],
}

@pytest.fixture
def scenario_db():
    engine = create_engine("sqlite+pysqlite://",
                           connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        category = Category(name="Catálogo controlado de 20 escenarios")
        db.add(category); db.flush()
        for name, variants in CATALOG.items():
            p = ProductService(name=name, kind="SERVICIO" if name=="Mantenimiento AC" else "PRODUCTO",
                               category_id=category.id)
            db.add(p); db.flush()
            for variant in variants:
                db.add(LexicalVariant(variant=variant, normalized_value=name,
                                      product_service_id=p.id, requires_confirmation=False))
        db.add(LexicalVariant(variant="compus", normalized_value="computadora",
                              product_service_id=None, requires_confirmation=True))
        db.add(LexicalVariant(variant="compu", normalized_value="computadora",
                              product_service_id=None, requires_confirmation=True))
        for brand in ["Dell", "Samsung"]:
            db.add(Brand(name=brand))
        db.commit()
        yield db
    engine.dispose()


@pytest.mark.parametrize("case_id,text,products,quantities,attributes", CASES, ids=[x[0] for x in CASES])
def test_reference_scenario_extraction(scenario_db, case_id, text, products, quantities, attributes):
    actual = NLPService(scenario_db).extract(text)
    observed = [x.product_name for x in actual]
    observed_qty = [x.quantity for x in actual]
    assert observed == products, (case_id, observed, products)
    assert observed_qty == quantities, (case_id, observed_qty, quantities)
    if case_id == "S05":
        assert [x.brand_name for x in actual] == ["Dell", "Samsung"]
        assert any(x.key=="ram" and x.normalized=="16 GB" for x in actual[0].characteristics)
        assert any(x.key=="tamano_pantalla" and x.normalized=="24 pulgadas" for x in actual[1].characteristics)
    if case_id in {"S07", "S11"}:
        assert [next((c.normalized for c in x.characteristics if c.key=="color"), None)
                for x in actual] == (["blanco","azul"] if case_id=="S07" else ["azul",None])
    if case_id == "S15":
        assert actual[0].ambiguities and actual[0].product_id is None
    if case_id == "S16":
        assert all(x.product_name != "Laptop" for x in actual)


def test_S13_requires_real_quantity(scenario_db):
    item = NLPService(scenario_db).extract("Necesito varias sillas para recepción.")[0]
    assert item.quantity is None


def test_S14_requires_catalog_mandatory_length(scenario_db):
    cable = scenario_db.query(ProductService).filter_by(name="Cable HDMI").one()
    length = Characteristic(name="Longitud", key="longitud")
    scenario_db.add(length); scenario_db.flush()
    template = RequirementTemplate(product_service_id=cable.id, name="Cable", active=True)
    scenario_db.add(template); scenario_db.flush()
    scenario_db.add(TemplateField(template_id=template.id, characteristic_id=length.id,
                                  required=True, question_text="¿Qué longitud necesita?"))
    user = LocalUser(username="escenario", display_name="Escenario", password_hash="dummy")
    scenario_db.add(user);scenario_db.commit()
    request = RequestService(scenario_db).create("Cotizar 3 cables HDMI.", user.id)
    assert any(q.field_key == "longitud" and q.status == "PENDIENTE"
               for q in request.items[0].questions)


def test_S16_no_provider_or_email_when_incomplete(scenario_db):
    printer = scenario_db.query(ProductService).filter_by(name="Impresora").one()
    compatibility = Characteristic(name="Equipo de destino", key="equipo_destino")
    scenario_db.add(compatibility); scenario_db.flush()
    template = RequirementTemplate(product_service_id=printer.id, name="Impresora", active=True)
    scenario_db.add(template); scenario_db.flush()
    scenario_db.add(TemplateField(template_id=template.id, characteristic_id=compatibility.id,
                                  required=True, question_text="¿Con qué equipo debe ser compatible?"))
    user = LocalUser(username="escenario", display_name="Escenario", password_hash="dummy")
    scenario_db.add(user); scenario_db.commit()
    request = RequestService(scenario_db).create(
        "Solicito 1 impresora compatible con mi equipo.", user.id)
    assert request.status != "COMPLETO"
    assert any(q.field_key=="equipo_destino" for q in request.items[0].questions)
    from app.services.providers import ProviderService
    with pytest.raises(ValueError, match="completos"):
        ProviderService(scenario_db).generate_for_request(request.id)
