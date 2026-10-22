"""OE3: integración HTTP con sesiones reales, base de datos aislada y SMTP falso."""
import os
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("SESSION_SECRET", "ci-private-only-test-session-secret")
from contextlib import contextmanager
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.seed import seed_database
from app.db.session import get_db
from app.models.domain import LocalUser
from app.services.auth import hash_password
import app.main as main_module


@pytest.fixture
def clients(monkeypatch):
    engine = create_engine("sqlite+pysqlite://",
                           connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as db:
        seed_database(db)
        for name, role in [("andrea", "USUARIO_FINAL"), ("usuario_b", "USUARIO_FINAL"),
                           ("admin", "ADMIN_GLOBAL")]:
            db.add(LocalUser(username=name, display_name=name, role=role,
                             password_hash=hash_password("ClaveSintetica1!")))
        db.commit()

    monkeypatch.setattr(main_module, "SessionLocal", factory)
    monkeypatch.setattr(main_module.settings, "auto_create_tables", False)
    monkeypatch.setattr(main_module.settings, "auth_enabled", True)
    monkeypatch.setattr(main_module.settings, "smtp_fernet_key", Fernet.generate_key().decode())

    def override_db():
        with factory() as db:
            yield db

    main_module.app.dependency_overrides[get_db] = override_db
    with TestClient(main_module.app) as a, TestClient(main_module.app) as b, TestClient(main_module.app) as admin:
        for client, name in [(a, "andrea"), (b, "usuario_b"), (admin, "admin")]:
            response = client.post("/api/auth/login", json={"username": name, "password": "ClaveSintetica1!"})
            assert response.status_code == 200, response.text
        yield a, b, admin, factory
    main_module.app.dependency_overrides.clear()
    engine.dispose()


def test_users_cannot_read_change_or_list_other_users_requests(clients):
    a, b, admin, _ = clients
    created = a.post("/api/solicitudes", json={"texto": "2 laptops y 3 monitores"})
    assert created.status_code == 200, created.text
    record = created.json()
    rid = record["id"]
    assert a.get(f"/api/solicitudes/{rid}").status_code == 200
    assert b.get(f"/api/solicitudes/{rid}").status_code == 404
    assert b.get(f"/api/solicitudes/{rid}/correos").status_code == 404
    assert b.get(f"/api/solicitudes/{rid}/proveedores").status_code == 404
    assert b.get(f"/api/solicitudes/{rid}/proformas").status_code == 404
    assert b.get(f"/api/solicitudes/{rid}/comparacion").status_code == 404
    assert b.post(f"/api/solicitudes/{rid}/proveedores").status_code == 404
    assert rid not in [row["id"] for row in b.get("/api/solicitudes/buscar").json()]
    question_id = record["articulos"][0]["preguntas"][0]["id"]
    assert b.post(f"/api/solicitudes/{rid}/respuestas",
                  json={"pregunta_id": question_id, "respuesta": "16 GB RAM"}).status_code == 404
    # La persona administradora tampoco accede al contenido privado de otra cuenta.
    assert admin.get(f"/api/solicitudes/{rid}").status_code == 404


def test_catalog_role_and_smtp_separation(clients):
    a, b, admin, _ = clients
    kwargs = {"files": {"file": ("prueba.csv", "name,email\nProveedor Prueba,prueba@example.test\n", "text/csv")}}
    assert a.post("/api/catalogo/importar?tipo=proveedores", **kwargs).status_code == 403
    assert b.post("/api/catalogo/importar?tipo=proveedores", **kwargs).status_code == 403
    # La decisión de autorización administrativa ocurre antes de procesar el CSV.
    assert admin.get("/api/catalogo").status_code != 403

    config = {"host": "smtp.example.test", "port": 587,
              "username": "andrea@example.test", "from_email": "andrea@example.test",
              "password": "credencial-sintetica", "use_tls": True}
    assert a.put("/api/smtp/mi-cuenta", json=config).status_code == 200
    first = a.get("/api/smtp/mi-cuenta").json()
    assert first["configurada"] is True
    assert "password" not in first and "password_encrypted" not in first
    assert b.get("/api/smtp/mi-cuenta").json() == {"configurada": False}


def test_complete_flow_two_items_validation_provider_email_mock(clients, monkeypatch):
    a, b, admin, factory = clients
    create = a.post("/api/solicitudes", json={"texto": "2 laptops Dell y 3 monitores"})
    assert create.status_code == 200, create.text
    data = create.json()
    assert len(data["articulos"]) == 2
    assert [str(x["cantidad"]) for x in data["articulos"]] == ["2.00", "3.00"]
    rid = data["id"]
    # Completar las plantillas dinámicas según el campo solicitado.
    for item in data["articulos"]:
        for q in [q for q in item["preguntas"] if q["status"] == "PENDIENTE"]:
            if q["field_key"] == "ram":
                answer = "16 GB RAM y 512 GB SSD"
            elif q["field_key"] == "tamano_pantalla":
                answer = "24 pulgadas"
            else:
                continue
            response = a.post(f"/api/solicitudes/{rid}/respuestas",
                              json={"pregunta_id": q["id"], "respuesta": answer})
            assert response.status_code == 200, response.text
            # Si RAM resolvió almacenamiento en la misma respuesta, no duplicarla.
            break
    # Completar preguntas restantes sin repetir las respondidas.
    updated = a.get(f"/api/solicitudes/{rid}").json()
    for item in updated["articulos"]:
        for q in [q for q in item["preguntas"] if q["status"] == "PENDIENTE"]:
            answer = {"almacenamiento": "512 GB SSD", "tamano_pantalla": "24 pulgadas"}.get(q["field_key"])
            assert answer is not None, q
            response = a.post(f"/api/solicitudes/{rid}/respuestas",
                              json={"pregunta_id": q["id"], "respuesta": answer})
            assert response.status_code == 200, response.text
    updated = a.get(f"/api/solicitudes/{rid}").json()
    assert updated["estado"] == "COMPLETO", updated
    providers = a.post(f"/api/solicitudes/{rid}/proveedores")
    assert providers.status_code == 200, providers.text
    rows = providers.json()
    assert rows
    # Separación por compatibilidad del catálogo, no enviar todos los artículos a todos.
    for pr in rows:
        draft = a.post(f"/api/solicitudes-proveedor/{pr['id']}/correo/borrador")
        assert draft.status_code == 200, draft.text
        email = draft.json()
        assert b.post(f"/api/correos/{email['id']}/autorizar").status_code == 404
        assert a.post(f"/api/correos/{email['id']}/enviar").status_code == 400

    assert a.put("/api/smtp/mi-cuenta", json={
        "host": "smtp.example.test", "port": 587,
        "username": "andrea@example.test", "from_email": "andrea@example.test",
        "password": "credencial-sintetica", "use_tls": True
    }).status_code == 200
    sent = []
    class FakeSMTP:
        def __init__(self, host, port, timeout):
            assert host == "smtp.example.test"
            assert port == 587
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def ehlo(self): pass
        def starttls(self): pass
        def login(self, username, password):
            assert (username, password) == ("andrea@example.test", "credencial-sintetica")
        def send_message(self, message):
            sent.append(message)

    monkeypatch.setattr("app.services.email_service.smtplib.SMTP", FakeSMTP)
    email_id = a.get(f"/api/solicitudes/{rid}/correos").json()[0]["id"]
    assert a.post(f"/api/correos/{email_id}/autorizar").status_code == 200
    assert a.post(f"/api/correos/{email_id}/enviar").status_code == 200
    assert len(sent) == 1
    assert b.get(f"/api/solicitudes/{rid}/correos").status_code == 404
