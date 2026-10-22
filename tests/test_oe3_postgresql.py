"""Verificación de esquema y migración OE3 en PostgreSQL real aislado en CI."""
import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.domain import LocalUser, Request, RequestItem, UnitMeasure


@pytest.fixture
def pg_engine():
    url = os.environ.get("OE3_POSTGRES_TEST_URL")
    if not url:
        pytest.skip("OE3_POSTGRES_TEST_URL no disponible: PostgreSQL no acreditado")
    engine = create_engine(url, pool_pre_ping=True)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA IF EXISTS oe3_audit CASCADE"))
        connection.execute(text("CREATE SCHEMA oe3_audit"))
    schema_engine = engine.execution_options(schema_translate_map={None: "oe3_audit"})
    # Las operaciones de migración usan search_path explícito hacia el esquema de prueba.
    try:
        yield engine
    finally:
        with engine.begin() as connection:
            connection.execute(text("DROP SCHEMA IF EXISTS oe3_audit CASCADE"))
        engine.dispose()


def test_manual_migration_from_legacy_schema(pg_engine):
    # Esquema histórico mínimo con dependencias para probar ALTER reales.
    with pg_engine.begin() as con:
        con.execute(text("SET LOCAL search_path TO oe3_audit"))
        for ddl in [
            "CREATE TABLE usuario_local (id SERIAL PRIMARY KEY, username VARCHAR(80) UNIQUE)",
            "CREATE TABLE solicitud (id SERIAL PRIMARY KEY, original_text TEXT)",
            "CREATE TABLE unidad_medida (id SERIAL PRIMARY KEY, symbol VARCHAR(20))",
            "CREATE TABLE articulo_solicitud (id SERIAL PRIMARY KEY, request_id INT REFERENCES solicitud(id))",
            "INSERT INTO usuario_local (username) VALUES ('a'), ('b')",
            "INSERT INTO solicitud (original_text) VALUES ('legado')",
            "INSERT INTO unidad_medida (symbol) VALUES ('unidad')",
        ]:
            con.execute(text(ddl))
    sql = Path("migrations/manual_oe3_20261022.sql").read_text()
    # La migración contiene BEGIN/COMMIT; la ejecutamos con conexión DBAPI aislada.
    with pg_engine.connect() as con:
        con.execute(text("SET search_path TO oe3_audit"))
        con.commit()
        con.exec_driver_sql(sql)
        con.commit()
    with pg_engine.begin() as con:
        con.execute(text("SET LOCAL search_path TO oe3_audit"))
        columns = con.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema='oe3_audit' AND table_name='solicitud'
        """)).scalars().all()
        assert "owner_user_id" in columns
        assert con.scalar(text("SELECT COUNT(*) FROM solicitud WHERE owner_user_id IS NULL")) == 1
        con.execute(text("UPDATE solicitud SET owner_user_id = (SELECT id FROM usuario_local WHERE username='a')"))
        assert con.scalar(text("SELECT COUNT(*) FROM solicitud WHERE owner_user_id IS NULL")) == 0
        assert con.scalar(text("SELECT role FROM usuario_local WHERE username='b'")) == "USUARIO_FINAL"
        con.execute(text("INSERT INTO smtp_cuenta_usuario(user_id,host,from_email) VALUES (1,'fake.test','a@fake.test')"))
        assert con.scalar(text("SELECT COUNT(*) FROM smtp_cuenta_usuario")) == 1
        # Los FK rechazan cualquier propietario inexistente.
        con.execute(text("SAVEPOINT sp_fk"))
        try:
            con.execute(text("UPDATE solicitud SET owner_user_id = 999999"))
        except Exception:
            con.execute(text("ROLLBACK TO SAVEPOINT sp_fk"))
        else:
            pytest.fail("Foreign key de propietario no protegida")
