"""Comprueba en una COPIA PostgreSQL que la migración OE3 no altera datos históricos.

Uso:
  OE3_COPY_DATABASE_URL='postgresql+psycopg://.../proformas_oe3_audit' \
    python scripts/verify_oe3_copy.py --apply --confirm-isolated-copy \
    --output informe_oe3_copia.json

REQUISITOS:
- La base debe ser una RESTAURACIÓN previa, nunca la instancia original.
- El nombre de la base debe terminar en _oe3_audit.
- NO subir el respaldo ni credenciales a GitHub.
- Produce recuentos y huellas SHA256 agregadas en memoria, sin exportar filas.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path
import secrets
import sys

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

MIGRATION = Path(__file__).resolve().parents[1] / "migrations" / "manual_oe3_20261022.sql"
LEGACY_TABLES = {"usuario_local", "solicitud", "articulo_solicitud", "unidad_medida"}


def sanitized(value):
    if isinstance(value, (bytes, memoryview)):
        return bytes(value).hex()
    if isinstance(value, Decimal):
        return str(value)
    return str(value) if not isinstance(value, (int, float, str, type(None), bool)) else value


def snapshot(engine, salt: bytes, original_columns=None):
    """Fingerprints order-independent of all existing rows, only original columns."""
    preparer = engine.dialect.identifier_preparer
    with engine.connect() as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        conn.execute(text("SET LOCAL statement_timeout = '120000ms'"))
        schema = conn.scalar(text("SELECT current_schema()"))
        inspector = inspect(conn)
        names = original_columns or {
            name: [col["name"] for col in inspector.get_columns(name, schema=schema)]
            for name in inspector.get_table_names(schema=schema)
        }
        output = {}
        for table, columns in names.items():
            # Quoted identifiers, never user-provided SQL expressions.
            safe_schema = preparer.quote_schema(schema)
            safe_table = preparer.quote(table)
            identifiers = ", ".join(preparer.quote(col) for col in columns)
            query = f"SELECT {identifiers} FROM {safe_schema}.{safe_table}"
            accumulator = 0
            count = 0
            cursor = conn.execution_options(stream_results=True).execute(text(query))
            while True:
                rows = cursor.fetchmany(250)
                if not rows:
                    break
                for row in rows:
                    serialized = json.dumps(
                        [sanitized(v) for v in row], ensure_ascii=False, separators=(",", ":")
                    ).encode("utf-8")
                    rowhash = sha256(salt + serialized).digest()
                    accumulator ^= int.from_bytes(rowhash, "big")
                    count += 1
            output[table] = {
                "columns": columns,
                "rows": count,
                "fingerprint": f"{accumulator:064x}",
            }
        conn.rollback()
    return output


def inspect_migration(engine):
    check = {}
    with engine.connect() as con:
        con.execute(text("SET TRANSACTION READ ONLY"))
        con.execute(text("SET LOCAL statement_timeout = '20000ms'"))
        schema = con.scalar(text("SELECT current_schema()"))
        tables = set(inspect(con).get_table_names(schema=schema))
        for t in ("usuario_local", "solicitud", "articulo_solicitud", "unidad_medida", "smtp_cuenta_usuario"):
            check[f"table_{t}"] = t in tables

        columns = {}
        for table, col in [
            ("usuario_local", "role"),
            ("solicitud", "owner_user_id"),
            ("articulo_solicitud", "unit_measure_id"),
            ("smtp_cuenta_usuario", "password_encrypted"),
        ]:
            columns[f"{table}.{col}"] = (
                table in tables and col in {
                    x["name"] for x in inspect(con).get_columns(table, schema=schema)
                }
            )
        check["new_columns"] = columns
        constraints = set(con.execute(text("""
            SELECT c.conname
            FROM pg_constraint c
            JOIN pg_class t ON t.oid = c.conrelid
            JOIN pg_namespace n ON n.oid=t.relnamespace
            WHERE n.nspname=:schema AND c.contype='f' AND c.convalidated
        """), {"schema": schema}).scalars())
        check["fk_owner_validated"] = "fk_solicitud_owner" in constraints
        check["fk_unit_validated"] = "fk_articulo_unidad" in constraints
        if columns["solicitud.owner_user_id"]:
            check["unassigned_legacy_requests"] = con.scalar(
                text("SELECT count(*) FROM solicitud WHERE owner_user_id IS NULL"))
            check["invalid_owners"] = con.scalar(text("""
                SELECT count(*) FROM solicitud s LEFT JOIN usuario_local u
                ON s.owner_user_id=u.id
                WHERE s.owner_user_id IS NOT NULL AND u.id IS NULL
            """))
        if columns["articulo_solicitud.unit_measure_id"]:
            check["unassigned_legacy_units"] = con.scalar(
                text("SELECT count(*) FROM articulo_solicitud WHERE unit_measure_id IS NULL"))
            check["invalid_units"] = con.scalar(text("""
                SELECT count(*) FROM articulo_solicitud a LEFT JOIN unidad_medida u
                ON a.unit_measure_id=u.id
                WHERE a.unit_measure_id IS NOT NULL AND u.id IS NULL
            """))
        if columns["usuario_local.role"]:
            check["invalid_roles"] = con.scalar(text("""
                SELECT count(*) FROM usuario_local
                WHERE role IS NULL OR role NOT IN ('ADMIN_GLOBAL','USUARIO_FINAL')
            """))
        con.rollback()
    return check


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Aplicar migración a copia y comparar")
    parser.add_argument("--confirm-isolated-copy", action="store_true")
    parser.add_argument("--output", default="informe_oe3_copia.json")
    args = parser.parse_args()
    url = os.environ.get("OE3_COPY_DATABASE_URL")
    if not url:
        raise RuntimeError("Falta OE3_COPY_DATABASE_URL, distinta de DATABASE_URL.")
    parsed = make_url(url)
    dbname = parsed.database or ""
    if not parsed.drivername.startswith("postgresql") or not dbname.endswith("_oe3_audit"):
        raise RuntimeError("Solo se permite PostgreSQL con nombre terminado en '_oe3_audit'.")
    prod = os.environ.get("DATABASE_URL")
    if prod and make_url(prod).set(drivername=parsed.drivername).render_as_string(hide_password=True) == parsed.render_as_string(hide_password=True):
        raise RuntimeError("La base de prueba coincide con DATABASE_URL; se rechazó.")
    if args.apply and not args.confirm_isolated_copy:
        raise RuntimeError("Falta --confirm-isolated-copy. No se ejecutó migración.")

    report = {
        "date_utc": datetime.now(timezone.utc).isoformat(),
        "database_name": dbname,
        "source": "RESTORED_COPY_USER_SUPPLIED_NOT_INFERRED",
        "migration_applied": False,
        "status": "NOT_RUN",
        "all_previous_rows_unchanged": None,
        "tables": {},
        "migration_checks": {},
        "warning": (
            "El operador debe acreditar que la base procede de un respaldo real; "
            "este programa no puede verificar la procedencia del respaldo."
        ),
    }
    engine = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 8})
    try:
        existing = set(inspect(engine).get_table_names())
        missing = LEGACY_TABLES - existing
        if missing:
            raise RuntimeError("Esquema incompleto en copia: " + ", ".join(sorted(missing)))
        salt = secrets.token_bytes(32)
        before = snapshot(engine, salt)
        if not args.apply:
            report["status"] = "BASELINE_ONLY"
        else:
            sql = MIGRATION.read_text(encoding="utf-8")
            with engine.connect() as con:
                con.exec_driver_sql(sql)
                con.commit()
            report["migration_applied"] = True
            after = snapshot(engine, salt, {table: data["columns"] for table, data in before.items()})
            report["tables"] = {
                name: {
                    "before": old["rows"], "after": after[name]["rows"],
                    "rows_unchanged": old["rows"] == after[name]["rows"],
                    "values_unchanged": old["fingerprint"] == after[name]["fingerprint"],
                }
                for name, old in before.items()
            }
            report["all_previous_rows_unchanged"] = all(
                row["rows_unchanged"] and row["values_unchanged"]
                for row in report["tables"].values()
            )
            report["migration_checks"] = inspect_migration(engine)
            c = report["migration_checks"]
            structural = (
                all(c["new_columns"].values())
                and c["fk_owner_validated"]
                and c["fk_unit_validated"]
                and all(c[f"table_{t}"] for t in ("smtp_cuenta_usuario",))
                and c.get("invalid_owners", 1) == 0
                and c.get("invalid_units", 1) == 0
                and c.get("invalid_roles", 1) == 0
            )
            report["status"] = (
                "PASSED_COPY" if report["all_previous_rows_unchanged"] and structural
                else "FAILED_COPY"
            )
    finally:
        engine.dispose()
    target = Path(args.output)
    target.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Resultado {report['status']}. Informe: {target}")
    print("Tablas históricas verificadas:", len(report["tables"]))
    return 0 if report["status"] in {"PASSED_COPY", "BASELINE_ONLY"} else 1


if __name__ == "__main__":
    try:
        sys.exit(run())
    except Exception as exc:
        # No registrar errores de conexión completos: pueden contener secretos.
        print("No se completó la auditoría: ", type(exc).__name__,
              file=sys.stderr)
        sys.exit(2)
