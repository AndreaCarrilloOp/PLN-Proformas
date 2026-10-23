"""Pruebas HTTP de CRUD OE4 y rechazo de PDF sin texto."""
import os
os.environ.setdefault("DATABASE_URL","sqlite+pysqlite:///:memory:")
os.environ.setdefault("SESSION_SECRET","oe4-only-testing")
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine,select
from sqlalchemy.orm import Session,sessionmaker
from sqlalchemy.pool import StaticPool
from app.db.base import Base
from app.db.session import get_db
from app.db.seed import seed_database
from app.models.domain import LocalUser,Quote,Request
from app.services.auth import hash_password
from app.main import app,settings

@pytest.fixture
def clients(monkeypatch):
    engine=create_engine("sqlite+pysqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sf=sessionmaker(bind=engine,expire_on_commit=False)
    with sf() as db:
        seed_database(db)
        db.add_all([LocalUser(username=name,display_name=name,password_hash=hash_password("Prueba12345!"),role=role) for name,role in [("admin_oe4","ADMIN_GLOBAL"),("user_oe4","USUARIO_FINAL")]])
        db.commit()
    def override():
        with sf() as db: yield db
    app.dependency_overrides[get_db]=override
    monkeypatch.setattr(settings,"auto_create_tables",False)
    with TestClient(app) as admin,TestClient(app) as user:
        for client,username in [(admin,"admin_oe4"),(user,"user_oe4")]:
            assert client.post("/api/auth/login",json={"username":username,"password":"Prueba12345!"}).status_code==200
        yield admin,user,sf
    app.dependency_overrides.clear()
    engine.dispose()

def test_admin_crud_and_denied_user(clients):
    admin,user,_=clients
    path="/api/catalogo/admin/proveedores"
    data={"nombre":"Proveedor OE4","correo":"oe4@example.test","activo":True}
    assert user.post(path,json=data).status_code==403
    assert user.get(path).status_code==403
    created=admin.post(path,json=data)
    assert created.status_code==201,created.text
    record=created.json()
    assert admin.post(path,json=data).status_code==409
    assert admin.get(f"{path}/{record['id']}").status_code==200
    updated=admin.put(f"{path}/{record['id']}",json={**data,"correo":"nuevo@example.test"})
    assert updated.status_code==200,updated.text
    assert updated.json()["correo"]=="nuevo@example.test"
    assert admin.delete(f"{path}/{record['id']}").json()["eliminacion"]=="DESACTIVADO"
    assert admin.get(f"{path}/{record['id']}").json()["activo"] is False

def test_category_brand_product_and_missing_relation(clients):
    admin,user,_=clients
    c=admin.post("/api/catalogo/admin/categorias",json={"nombre":"OE4 Categoría"})
    assert c.status_code==201,c.text
    cid=c.json()["id"]
    p=admin.post("/api/catalogo/admin/productos",json={"nombre":"OE4 Equipo","categoria_id":cid,"tipo":"PRODUCTO"})
    assert p.status_code==201,p.text
    pid=p.json()["id"]
    assert admin.post("/api/catalogo/admin/productos",json={"nombre":"OE4 Fallido","categoria_id":999999}).status_code==400
    assert admin.delete(f"/api/catalogo/admin/categorias/{cid}").status_code==409
    assert admin.delete(f"/api/catalogo/admin/productos/{pid}").json()["eliminacion"]=="DESACTIVADO"
    brand=admin.post("/api/catalogo/admin/marcas",json={"nombre":"Marca OE4"})
    assert brand.status_code==201,brand.text
    assert admin.delete(f"/api/catalogo/admin/marcas/{brand.json()['id']}").status_code==200

def test_pdf_nonselectable_not_persisted(clients):
    _,user,sf=clients
    with sf() as db:
        owner=db.scalar(select(LocalUser).where(LocalUser.username=="user_oe4"))
        req=Request(original_text="Necesito 2 monitores",owner_user_id=owner.id,status="COMPLETO")
        db.add(req);db.commit();rid=req.id
    # PDF sintético formalmente válido con página sin texto.
    from io import BytesIO
    from reportlab.pdfgen import canvas
    output=BytesIO()
    pdf=canvas.Canvas(output)
    pdf.rect(20,20,120,120)
    pdf.showPage();pdf.save()
    upload=user.post(f"/api/solicitudes/{rid}/proformas",files={"file":("sin-texto.pdf",output.getvalue(),"application/pdf")})
    assert upload.status_code==400,upload.text
    assert "texto seleccionable" in upload.text
    with sf() as db:
        assert db.scalar(select(Quote).where(Quote.request_id==rid)) is None

def test_csv_role_and_import(clients):
    admin,user,_=clients
    file={"file":("proveedores.csv",b"name,email\nProveedor OE4 CSV,proveedor@example.test\n","text/csv")}
    assert user.post("/api/catalogo/importar?tipo=proveedores",files=file).status_code==403
    assert admin.post("/api/catalogo/importar?tipo=proveedores",files=file).status_code==200
