from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.auth import hash_password

from app.models.domain import (
    Brand,
    Category,
    Characteristic,
    LexicalVariant,
    LocalUser,
    ProductBrand,
    ProductService,
    Provider,
    ProviderProductService,
    RequirementTemplate,
    TemplateField,
    UnitMeasure,
)


def _get_or_create(db: Session, model, defaults=None, **kwargs):
    obj = db.scalar(select(model).filter_by(**kwargs))
    if obj:
        return obj
    obj = model(**kwargs, **(defaults or {}))
    db.add(obj)
    db.flush()
    return obj


def seed_database(db: Session) -> None:
    settings = get_settings()
    if settings.local_auth_username and settings.local_auth_password:
        username = settings.local_auth_username.strip().lower()
        existing_user = db.scalar(select(LocalUser).where(LocalUser.username == username))
        if not existing_user:
            db.add(LocalUser(
                username=username,
                display_name=settings.local_auth_display_name.strip() or username,
                password_hash=hash_password(settings.local_auth_password),
                active=True,
            ))
            db.flush()

    laptops_cat = _get_or_create(db, Category, name="Computadoras portátiles")
    monitors_cat = _get_or_create(db, Category, name="Monitores")

    laptop = _get_or_create(db, ProductService, category_id=laptops_cat.id, name="Laptop", kind="PRODUCTO")
    monitor = _get_or_create(db, ProductService, category_id=monitors_cat.id, name="Monitor", kind="PRODUCTO")

    for variant, normalized, product, confirm in [
        ("laptop", "Laptop", laptop, False),
        ("laptops", "Laptop", laptop, False),
        ("portátil", "Laptop", laptop, False),
        ("portátiles", "Laptop", laptop, False),
        ("computadora portátil", "Laptop", laptop, False),
        ("computadoras portátiles", "Laptop", laptop, False),
        ("monitor", "Monitor", monitor, False),
        ("monitores", "Monitor", monitor, False),
        ("compu", "computadora", None, True),
        ("compus", "computadora", None, True),
        ("computadora", "computadora", None, True),
        ("computadoras", "computadora", None, True),
    ]:
        _get_or_create(
            db,
            LexicalVariant,
            variant=variant,
            defaults={
                "normalized_value": normalized,
                "product_service_id": product.id if product else None,
                "requires_confirmation": confirm,
                "transformation_type": "VARIANTE_LEXICA",
            },
        )

    brands = {name: _get_or_create(db, Brand, name=name) for name in ["Dell", "Lenovo", "HP", "Samsung"]}
    for brand in brands.values():
        for product in (laptop, monitor):
            _get_or_create(db, ProductBrand, product_service_id=product.id, brand_id=brand.id)

    characteristics = {}
    for key, name in [
        ("ram", "RAM"),
        ("almacenamiento", "Almacenamiento"),
        ("procesador", "Procesador"),
        ("tamano_pantalla", "Tamaño de pantalla"),
    ]:
        characteristics[key] = _get_or_create(db, Characteristic, key=key, name=name)

    _get_or_create(db, UnitMeasure, name="Unidad", symbol="unidad")
    _get_or_create(db, UnitMeasure, name="Gigabyte", symbol="GB")
    _get_or_create(db, UnitMeasure, name="Terabyte", symbol="TB")
    _get_or_create(db, UnitMeasure, name="Pulgada", symbol="in")

    laptop_template = db.scalar(select(RequirementTemplate).where(RequirementTemplate.product_service_id == laptop.id))
    if not laptop_template:
        laptop_template = RequirementTemplate(product_service_id=laptop.id, name="Requisitos mínimos para laptops")
        db.add(laptop_template)
        db.flush()
        db.add_all([
            TemplateField(template_id=laptop_template.id, characteristic_id=characteristics["ram"].id, required=True, question_text="¿Cuánta memoria RAM necesitan las laptops?"),
            TemplateField(template_id=laptop_template.id, characteristic_id=characteristics["almacenamiento"].id, required=True, question_text="¿Qué capacidad y tipo de almacenamiento necesitan las laptops?"),
        ])

    monitor_template = db.scalar(select(RequirementTemplate).where(RequirementTemplate.product_service_id == monitor.id))
    if not monitor_template:
        monitor_template = RequirementTemplate(product_service_id=monitor.id, name="Requisitos mínimos para monitores")
        db.add(monitor_template)
        db.flush()
        db.add(TemplateField(template_id=monitor_template.id, characteristic_id=characteristics["tamano_pantalla"].id, required=True, question_text="¿Qué tamaño de pantalla requieren los monitores?"))

    providers = {
        "Proveedor A": _get_or_create(db, Provider, name="Proveedor A", defaults={"email": "proveedor.a@example.com"}),
        "Proveedor B": _get_or_create(db, Provider, name="Proveedor B", defaults={"email": "proveedor.b@example.com"}),
        "Proveedor C": _get_or_create(db, Provider, name="Proveedor C", defaults={"email": "proveedor.c@example.com"}),
    }
    for provider_name, product in [
        ("Proveedor A", laptop), ("Proveedor A", monitor),
        ("Proveedor B", laptop),
        ("Proveedor C", monitor),
    ]:
        _get_or_create(db, ProviderProductService, provider_id=providers[provider_name].id, product_service_id=product.id)

    db.commit()
