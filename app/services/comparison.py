from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.domain import Quote, QuoteDetail


def comparison_for_request(db: Session, request_id: int) -> list[dict]:
    details = db.scalars(select(QuoteDetail).join(Quote).where(Quote.request_id == request_id, Quote.status == "VALIDADA")).all()
    return [{
        "producto": d.product_service.name if d.product_service else d.description,
        "proveedor": d.quote.provider.name if d.quote.provider else "Sin identificar",
        "cantidad": d.quantity,
        "precio_unitario": d.unit_price,
        "precio_total": d.total_price,
        "caracteristicas": d.features_text,
    } for d in details]
