from decimal import Decimal
from pydantic import BaseModel, Field


class QuoteDetailInput(BaseModel):
    producto_servicio_id: int | None = None
    descripcion: str = Field(min_length=1, max_length=300)
    cantidad: Decimal | None = None
    precio_unitario: Decimal | None = None
    precio_total: Decimal | None = None
    caracteristicas: str | None = None


class QuoteValidationInput(BaseModel):
    proveedor_id: int | None = None
    detalles: list[QuoteDetailInput]
