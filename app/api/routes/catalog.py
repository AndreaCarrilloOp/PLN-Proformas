from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.security import require_admin
from app.models.domain import LocalUser
from app.models.domain import Brand, Category, Characteristic, LexicalVariant, ProductService, Provider, RequirementTemplate, UnitMeasure
from app.services.import_service import CatalogImportService, SUPPORTED_TYPES

router = APIRouter(prefix="/catalogo", tags=["Catálogo"])


@router.get("/resumen")
def summary(db: Session = Depends(get_db)):
    return {
        "categorias": db.scalar(select(func.count()).select_from(Category)),
        "productos": db.scalar(select(func.count()).select_from(ProductService)),
        "marcas": db.scalar(select(func.count()).select_from(Brand)),
        "proveedores": db.scalar(select(func.count()).select_from(Provider)),
        "variantes": db.scalar(select(func.count()).select_from(LexicalVariant)),
        "plantillas": db.scalar(select(func.count()).select_from(RequirementTemplate)),
    }


@router.get("")
def list_catalog(tipo: str = Query(pattern="^(categorias|productos|marcas|proveedores|variantes|caracteristicas|unidades|plantillas)$"), db: Session = Depends(get_db)):
    if tipo == "categorias":
        return [{"id": x.id, "nombre": x.name} for x in db.scalars(select(Category).order_by(Category.name)).all()]
    if tipo == "productos":
        return [{"id": x.id, "nombre": x.name, "tipo": x.kind, "categoria": x.category.name if x.category else None} for x in db.scalars(select(ProductService).order_by(ProductService.name)).all()]
    if tipo == "marcas":
        return [{"id": x.id, "nombre": x.name} for x in db.scalars(select(Brand).order_by(Brand.name)).all()]
    if tipo == "proveedores":
        return [{"id": x.id, "nombre": x.name, "email": x.email, "activo": x.active} for x in db.scalars(select(Provider).order_by(Provider.name)).all()]
    if tipo == "variantes":
        return [{"id": x.id, "variante": x.variant, "normalizado": x.normalized_value, "requiere_confirmacion": x.requires_confirmation} for x in db.scalars(select(LexicalVariant).order_by(LexicalVariant.variant)).all()]
    if tipo == "caracteristicas":
        return [{"id": x.id, "key": x.key, "nombre": x.name} for x in db.scalars(select(Characteristic).order_by(Characteristic.name)).all()]
    if tipo == "unidades":
        return [{"id": x.id, "nombre": x.name, "simbolo": x.symbol} for x in db.scalars(select(UnitMeasure).order_by(UnitMeasure.name)).all()]
    return [{"id": x.id, "nombre": x.name, "producto": x.product_service.name} for x in db.scalars(select(RequirementTemplate).order_by(RequirementTemplate.name)).all()]


@router.post("/importar")
async def import_catalog(
    tipo: str = Query(),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: LocalUser = Depends(require_admin),
):
    if tipo not in SUPPORTED_TYPES:
        raise HTTPException(400, f"Tipo no soportado. Opciones: {', '.join(sorted(SUPPORTED_TYPES))}")
    content = await file.read()
    if len(content) > 2 * 1024 * 1024:
        raise HTTPException(413, "El archivo supera 2 MB")
    try:
        count = CatalogImportService(db).import_bytes(file.filename or "catalogo", content, tipo)
        return {"importados": count, "tipo": tipo}
    except (ValueError, UnicodeDecodeError) as exc:
        db.rollback()
        raise HTTPException(400, str(exc)) from exc
