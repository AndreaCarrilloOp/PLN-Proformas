"""Auditoría SOLO LECTURA de PostgreSQL persistente (OE3).

Ejecutar LOCALMENTE con DATABASE_URL en .env:
    python scripts/audit_persistent_oe3.py --output reporte_oe3_persistente.json

No solicita ni muestra contraseñas y no escribe registros en PostgreSQL.
NO equivale a ejecutar la migración ni a verificar un respaldo restaurado.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url

from app.core.config import get_settings

TABLES = [
    "usuario_local", "solicitud", "articulo_solicitud",
    "unidad_medida", "smtp_cuenta_usuario",
]


def audit():
    settings = get_settings()
    url = settings.sqlalchemy_database_url
    if not url.startswith(("postgresql://", "postgresql+psycopg://")):
        raise RuntimeError("La auditoría requiere PostgreSQL; se rechaza SQLite.")
    # No colocar la URL con credenciales en informes o salidas.
    engine = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 8})
    report = {
        "fecha_utc": datetime.now(timezone.utc).isoformat(),
        "motor": "PostgreSQL",
        "modo": "SOLO LECTURA (transacción READ ONLY)",
        "contexto": "BD configurada localmente; no exporta contenido ni identificadores",
        "resumen": {}, "comprobaciones": [], "advertencias": []
    }

    def check(name, status, detail, **counts):
        report["comprobaciones"].append({
            "nombre": name, "estado": status, "detalle": detail, **counts
        })

    try:
        with engine.connect() as conn:
            conn.execute(text("SET TRANSACTION READ ONLY"))
            conn.execute(text("SET LOCAL statement_timeout = '15000ms'"))
            schema = conn.scalar(text("SELECT current_schema()"))
            columns = {
                t: set(conn.execute(text("""
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema=:schema AND table_name=:table
                """), {"schema": schema, "table": t}).scalars())
                for t in TABLES
            }
            tables = {t for t, cols in columns.items() if cols}
            for t in TABLES:
                check(f"Tabla {t}", "OK" if t in tables else "FALTA",
                      "Presente en el esquema activo" if t in tables else "Ausente del esquema activo")
            required = {
                "usuario_local": "role",
                "solicitud": "owner_user_id",
                "articulo_solicitud": "unit_measure_id",
                "smtp_cuenta_usuario": "password_encrypted",
            }
            for t, c in required.items():
                check(f"Columna {t}.{c}", "OK" if c in columns[t] else "FALTA",
                      "Disponible" if c in columns[t] else "No está disponible")

            for t in TABLES:
                if t in tables:
                    report["resumen"][f"registros_{t}"] = conn.scalar(
                        text(f'SELECT COUNT(*) FROM "{t}"'))
            if {"usuario_local", "solicitud"} <= tables and "owner_user_id" in columns["solicitud"]:
                no_owner = conn.scalar(text("SELECT COUNT(*) FROM solicitud WHERE owner_user_id IS NULL"))
                invalid_owner = conn.scalar(text("""
                    SELECT COUNT(*) FROM solicitud s
                    LEFT JOIN usuario_local u ON u.id=s.owner_user_id
                    WHERE s.owner_user_id IS NOT NULL AND u.id IS NULL
                """))
                check("Solicitudes sin titular", "ATENCIÓN" if no_owner else "OK",
                      "No asignar automáticamente titulares históricos",
                      cantidad=no_owner)
                check("Integridad de propietario", "OK" if not invalid_owner else "ERROR",
                      "Comprobación de asociación a usuarios existentes", invalidos=invalid_owner)

            if "role" in columns["usuario_local"]:
                bad_roles = conn.scalar(text("""
                    SELECT COUNT(*) FROM usuario_local
                    WHERE role IS NULL OR role NOT IN ('ADMIN_GLOBAL','USUARIO_FINAL')
                """))
                check("Roles válidos", "OK" if bad_roles == 0 else "ERROR",
                      "ADMIN_GLOBAL / USUARIO_FINAL", invalidos=bad_roles)

            if {"articulo_solicitud", "unidad_medida"} <= tables and "unit_measure_id" in columns["articulo_solicitud"]:
                missing_units = conn.scalar(text(
                    "SELECT COUNT(*) FROM articulo_solicitud WHERE unit_measure_id IS NULL"))
                broken_units = conn.scalar(text("""
                    SELECT COUNT(*) FROM articulo_solicitud a
                    LEFT JOIN unidad_medida u ON a.unit_measure_id=u.id
                    WHERE a.unit_measure_id IS NOT NULL AND u.id IS NULL
                """))
                check("Artículos sin unidad", "ATENCIÓN" if missing_units else "OK",
                      "Las filas heredadas pueden necesitar revisión controlada",
                      cantidad=missing_units)
                check("Integridad de unidad", "OK" if not broken_units else "ERROR",
                      "Unidad vinculada a catálogo existente", invalidos=broken_units)
                available = set(conn.execute(text("SELECT symbol FROM unidad_medida")).scalars())
                expected = {"unidad", "caja", "resma", "paquete", "servicio"}
                check("Catálogo de unidades", "OK" if expected <= available else "ATENCIÓN",
                      "Se verifica presencia, no cantidad ni equivalencias",
                      faltantes=sorted(expected - available))

            constraints = set(conn.execute(text("""
                SELECT c.conname
                FROM pg_constraint c
                JOIN pg_class t ON t.oid=c.conrelid
                JOIN pg_namespace n ON n.oid=t.relnamespace
                WHERE n.nspname=:schema AND c.contype='f'
            """), {"schema": schema}).scalars())
            for name in ("fk_solicitud_owner", "fk_articulo_unidad"):
                check(f"Restricción {name}",
                      "OK" if name in constraints else "FALTA",
                      "Restricción referencial de migración OE3")

            if "smtp_cuenta_usuario" in tables:
                accounts = conn.execute(text("""
                    SELECT password_encrypted FROM smtp_cuenta_usuario
                    WHERE password_encrypted IS NOT NULL
                """)).scalars().all()
                key = settings.smtp_fernet_key
                if accounts and key:
                    valid = 0
                    for token in accounts:
                        try:
                            Fernet(key.encode()).decrypt(token.encode())
                            valid += 1
                        except (ValueError, InvalidToken):
                            pass
                    check("Descifrado de credenciales SMTP", "OK" if valid == len(accounts) else "ERROR",
                          "Validación local, sin registrar contraseñas",
                          cuentas_verificadas=valid, cuentas_con_clave=len(accounts))
                else:
                    check("Descifrado de credenciales SMTP", "NO APLICA",
                          "Sin claves de cuenta o sin SMTP_FERNET_KEY configurada",
                          cuentas_con_clave=len(accounts))
            conn.rollback()
    finally:
        engine.dispose()

    states = [x["estado"] for x in report["comprobaciones"]]
    report["estado_global"] = (
        "NO CONFORME" if any(x in {"FALTA", "ERROR"} for x in states)
        else "CON OBSERVACIONES" if "ATENCIÓN" in states
        else "CONFORME EN LAS COMPROBACIONES REALIZADAS"
    )
    report["advertencias"] = [
        "No se probaron cambios de datos: auditoría de lectura.",
        "No se acredita restauración ni migración histórica sin ejecutar dichas operaciones en una copia.",
        "El archivo JSON evita identificadores personales, textos de solicitudes y secretos.",
    ]
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="reporte_oe3_persistente.json")
    args = parser.parse_args()
    try:
        result = audit()
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print("Auditoría completada:", result["estado_global"], "| Informe:", target)
        print("Comprobaciones:", len(result["comprobaciones"]))
    except Exception as exc:
        # Las excepciones de conexión pueden incluir credenciales: nunca imprimir str(exc).
        print("La comprobación no pudo completarse. Clase de error:", type(exc).__name__)
        raise SystemExit(2)
