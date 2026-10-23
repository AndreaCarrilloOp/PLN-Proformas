"""CRUD administrativo OE4. No se eliminan físicamente productos ni proveedores
porque pueden estar referenciados por solicitudes, proformas y correos históricos.
"""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.security import require_admin
from app.db.session import get_db
from app.models.domain import (
    Brand, Category, LocalUser, ProductService, Provider,
)

router = APIRouter(prefix="/catalogo/admin", tags=["Administración de catálogos"])
CatalogType = Literal["categorias", "productos", "marcas", "proveedores"]
MODELS = {
    "categorias": Category, "productos": ProductService,
    "marcas": Brand, "proveedores": Provider,
}


class CategoryData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nombre: str = Field(min_length=1, max_length=120)


class BrandData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nombre: str = Field(min_length=1, max_length=100)


class ProductData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nombre: str = Field(min_length=1, max_length=120)
    categoria_id: int | None = Field(default=None, gt=0)
    tipo: Literal["PRODUCTO", "SERVICIO"] = "PRODUCTO"
    activo: bool = True


class ProviderData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nombre: str = Field(min_length=1, max_length=150)
    correo: str = Field(min_length=5, max_length=200, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    activo: bool = True


PAYLOAD = {
    "categorias": CategoryData, "productos": ProductData,
    "marcas": BrandData, "proveedores": ProviderData,
}


def _serialize(tipo: CatalogType, record):
    result = {"id": record.id, "nombre": record.name}
    if tipo == "productos":
        result.update(categoria_id=record.category_id, tipo=record.kind, activo=record.active)
    if tipo == "proveedores":
        result.update(correo=record.email, activo=record.active)
    return result


def _attributes(tipo: CatalogType, data: dict, db: Session):
    name = data["nombre"].strip()
    if not name:
        raise HTTPException(422, "El nombre no puede estar vacío")
    result = {"name": name}
    if tipo == "productos":
        category_id = data["categoria_id"]
        if category_id is not None and db.get(Category, category_id) is None:
            raise HTTPException(400, "Categoría no encontrada")
        result.update(category_id=category_id, kind=data["tipo"], active=data["activo"])
    elif tipo == "proveedores":
        result.update(email=data["correo"].strip(), active=data["activo"])
    return result


def _payload(tipo: CatalogType, body: dict, db: Session):
    try:
        normalized = PAYLOAD[tipo].model_validate(body)
    except Exception as exc:
        from pydantic import ValidationError
        if isinstance(exc, ValidationError):
            raise HTTPException(422, "Datos inválidos para el tipo de catálogo") from exc
        raise
    return _attributes(tipo, normalized.model_dump(), db)


def _commit(db: Session):
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "El registro está duplicado o tiene referencias que impiden la operación") from exc


@router.get("/{tipo}")
def list_admin_catalog(
    tipo: CatalogType, db: Session = Depends(get_db),
    user: LocalUser = Depends(require_admin),
):
    records = db.scalars(select(MODELS[tipo]).order_by(MODELS[tipo].id)).all()
    return [_serialize(tipo, r) for r in records]


@router.get("/{tipo}/{record_id}")
def get_admin_record(
    tipo: CatalogType, record_id: int,
    db: Session = Depends(get_db),
    user: LocalUser = Depends(require_admin),
):
    record = db.get(MODELS[tipo], record_id)
    if not record:
        raise HTTPException(404, "Registro no encontrado")
    return _serialize(tipo, record)


@router.post("/{tipo}", status_code=201)
def create_admin_record(
    tipo: CatalogType, body: dict, db: Session = Depends(get_db),
    user: LocalUser = Depends(require_admin),
):
    data = _payload(tipo, body, db)
    model = MODELS[tipo]
    duplicate = db.scalar(select(model.id).where(model.name.ilike(data["name"])))
    if duplicate is not None:
        raise HTTPException(409, "Ya existe un registro con ese nombre")
    record = model(**data)
    db.add(record)
    _commit(db)
    db.refresh(record)
    return _serialize(tipo, record)


@router.put("/{tipo}/{record_id}")
def update_admin_record(
    tipo: CatalogType, record_id: int, body: dict,
    db: Session = Depends(get_db),
    user: LocalUser = Depends(require_admin),
):
    record = db.get(MODELS[tipo], record_id)
    if not record:
        raise HTTPException(404, "Registro no encontrado")
    data = _payload(tipo, body, db)
    duplicate = db.scalar(
        select(MODELS[tipo].id).where(
            MODELS[tipo].name.ilike(data["name"]), MODELS[tipo].id != record_id
        )
    )
    if duplicate is not None:
        raise HTTPException(409, "Ya existe otro registro con ese nombre")
    for key, value in data.items():
        setattr(record, key, value)
    _commit(db)
    return _serialize(tipo, record)


@router.delete("/{tipo}/{record_id}")
def delete_admin_record(
    tipo: CatalogType, record_id: int, db: Session = Depends(get_db),
    user: LocalUser = Depends(require_admin),
):
    record = db.get(MODELS[tipo], record_id)
    if record is None:
        raise HTTPException(404, "Registro no encontrado")
    if tipo in ("productos", "proveedores"):
        record.active = False
        _commit(db)
        return {"id": record_id, "eliminacion": "DESACTIVADO"}
    try:
        db.delete(record)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "No se puede eliminar: el registro tiene referencias relacionadas") from exc
    return {"id": record_id, "eliminacion": "ELIMINADO"}
