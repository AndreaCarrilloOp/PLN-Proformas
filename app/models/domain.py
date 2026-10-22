from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class LocalUser(Base):
    __tablename__ = "usuario_local"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    role: Mapped[str] = mapped_column(String(24), nullable=False, default="USUARIO_FINAL", server_default="USUARIO_FINAL")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserSmtpAccount(Base):
    """Configuración por usuario; la clave se almacena cifrada con Fernet."""
    __tablename__ = "smtp_cuenta_usuario"
    user_id: Mapped[int] = mapped_column(ForeignKey("usuario_local.id"), primary_key=True)
    host: Mapped[str] = mapped_column(String(200))
    port: Mapped[int] = mapped_column(default=587)
    username: Mapped[str | None] = mapped_column(String(200), nullable=True)
    from_email: Mapped[str] = mapped_column(String(200))
    password_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    use_tls: Mapped[bool] = mapped_column(Boolean, default=True)


class Category(Base):
    __tablename__ = "categoria"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    products: Mapped[list[ProductService]] = relationship(back_populates="category")


class ProductService(Base):
    __tablename__ = "producto_servicio"
    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categoria.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(20), default="PRODUCTO")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    category: Mapped[Category | None] = relationship(back_populates="products")
    variants: Mapped[list[LexicalVariant]] = relationship(back_populates="product_service", cascade="all, delete-orphan")
    templates: Mapped[list[RequirementTemplate]] = relationship(back_populates="product_service", cascade="all, delete-orphan")


class LexicalVariant(Base):
    __tablename__ = "variante_lexica"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_service_id: Mapped[int | None] = mapped_column(ForeignKey("producto_servicio.id"), nullable=True)
    variant: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    normalized_value: Mapped[str] = mapped_column(String(120))
    transformation_type: Mapped[str] = mapped_column(String(60), default="VARIANTE_LEXICA")
    requires_confirmation: Mapped[bool] = mapped_column(Boolean, default=False)
    product_service: Mapped[ProductService | None] = relationship(back_populates="variants")


class Brand(Base):
    __tablename__ = "marca"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)


class ProductBrand(Base):
    __tablename__ = "producto_marca"
    product_service_id: Mapped[int] = mapped_column(ForeignKey("producto_servicio.id"), primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("marca.id"), primary_key=True)


class Characteristic(Base):
    __tablename__ = "caracteristica"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    key: Mapped[str] = mapped_column(String(80), unique=True, index=True)


class UnitMeasure(Base):
    __tablename__ = "unidad_medida"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    symbol: Mapped[str] = mapped_column(String(20), unique=True)


class RequirementTemplate(Base):
    __tablename__ = "plantilla"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_service_id: Mapped[int] = mapped_column(ForeignKey("producto_servicio.id"), index=True)
    name: Mapped[str] = mapped_column(String(150))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    product_service: Mapped[ProductService] = relationship(back_populates="templates")
    fields: Mapped[list[TemplateField]] = relationship(back_populates="template", cascade="all, delete-orphan")


class TemplateField(Base):
    __tablename__ = "plantilla_campo"
    id: Mapped[int] = mapped_column(primary_key=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("plantilla.id"), index=True)
    characteristic_id: Mapped[int] = mapped_column(ForeignKey("caracteristica.id"))
    required: Mapped[bool] = mapped_column(Boolean, default=True)
    conditional_rule: Mapped[str | None] = mapped_column(String(250), nullable=True)
    question_text: Mapped[str] = mapped_column(String(250))
    template: Mapped[RequirementTemplate] = relationship(back_populates="fields")
    characteristic: Mapped[Characteristic] = relationship()


class Provider(Base):
    __tablename__ = "proveedor"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class ProviderProductService(Base):
    __tablename__ = "proveedor_producto_servicio"
    provider_id: Mapped[int] = mapped_column(ForeignKey("proveedor.id"), primary_key=True)
    product_service_id: Mapped[int] = mapped_column(ForeignKey("producto_servicio.id"), primary_key=True)


class Request(Base):
    __tablename__ = "solicitud"
    id: Mapped[int] = mapped_column(primary_key=True)
    original_text: Mapped[str] = mapped_column(Text)
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("usuario_local.id"), index=True, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="PENDIENTE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    items: Mapped[list[RequestItem]] = relationship(back_populates="request", cascade="all, delete-orphan")


class RequestItem(Base):
    __tablename__ = "articulo_solicitud"
    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("solicitud.id"), index=True)
    product_service_id: Mapped[int | None] = mapped_column(ForeignKey("producto_servicio.id"), nullable=True)
    original_fragment: Mapped[str] = mapped_column(Text)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    unit_measure_id: Mapped[int | None] = mapped_column(ForeignKey("unidad_medida.id"), nullable=True)
    unit_measure: Mapped[UnitMeasure | None] = relationship()
    brand_id: Mapped[int | None] = mapped_column(ForeignKey("marca.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="PENDIENTE")
    request: Mapped[Request] = relationship(back_populates="items")
    product_service: Mapped[ProductService | None] = relationship()
    brand: Mapped[Brand | None] = relationship()
    characteristics: Mapped[list[ItemCharacteristic]] = relationship(back_populates="item", cascade="all, delete-orphan")
    questions: Mapped[list[ValidationQuestion]] = relationship(back_populates="item", cascade="all, delete-orphan")
    transformations: Mapped[list[Transformation]] = relationship(back_populates="item", cascade="all, delete-orphan")


class ItemCharacteristic(Base):
    __tablename__ = "articulo_caracteristica"
    __table_args__ = (UniqueConstraint("request_item_id", "characteristic_id", name="uq_item_characteristic"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    request_item_id: Mapped[int] = mapped_column(ForeignKey("articulo_solicitud.id"), index=True)
    characteristic_id: Mapped[int] = mapped_column(ForeignKey("caracteristica.id"))
    original_value: Mapped[str] = mapped_column(String(250))
    normalized_value: Mapped[str] = mapped_column(String(250))
    source: Mapped[str] = mapped_column(String(80))
    confirmed: Mapped[bool] = mapped_column(Boolean, default=True)
    item: Mapped[RequestItem] = relationship(back_populates="characteristics")
    characteristic: Mapped[Characteristic] = relationship()


class ValidationQuestion(Base):
    __tablename__ = "pregunta_validacion"
    id: Mapped[int] = mapped_column(primary_key=True)
    request_item_id: Mapped[int] = mapped_column(ForeignKey("articulo_solicitud.id"), index=True)
    field_key: Mapped[str] = mapped_column(String(100))
    question_text: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(30), default="PENDIENTE")
    item: Mapped[RequestItem] = relationship(back_populates="questions")
    responses: Mapped[list[ValidationResponse]] = relationship(back_populates="question", cascade="all, delete-orphan")


class ValidationResponse(Base):
    __tablename__ = "respuesta_validacion"
    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("pregunta_validacion.id"), index=True)
    response_text: Mapped[str] = mapped_column(Text)
    normalized_value: Mapped[str | None] = mapped_column(String(250), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    question: Mapped[ValidationQuestion] = relationship(back_populates="responses")


class Transformation(Base):
    __tablename__ = "transformacion"
    id: Mapped[int] = mapped_column(primary_key=True)
    request_item_id: Mapped[int | None] = mapped_column(ForeignKey("articulo_solicitud.id"), nullable=True, index=True)
    field_name: Mapped[str] = mapped_column(String(100))
    original_value: Mapped[str] = mapped_column(String(250))
    normalized_value: Mapped[str | None] = mapped_column(String(250), nullable=True)
    source: Mapped[str] = mapped_column(String(80))
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    item: Mapped[RequestItem | None] = relationship(back_populates="transformations")


class ProviderRequest(Base):
    __tablename__ = "solicitud_proveedor"
    __table_args__ = (UniqueConstraint("request_id", "provider_id", name="uq_request_provider"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("solicitud.id"), index=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("proveedor.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="BORRADOR")
    provider: Mapped[Provider] = relationship()
    request: Mapped[Request] = relationship()
    items: Mapped[list[ProviderRequestItem]] = relationship(back_populates="provider_request", cascade="all, delete-orphan")


class ProviderRequestItem(Base):
    __tablename__ = "solicitud_proveedor_articulo"
    provider_request_id: Mapped[int] = mapped_column(ForeignKey("solicitud_proveedor.id"), primary_key=True)
    request_item_id: Mapped[int] = mapped_column(ForeignKey("articulo_solicitud.id"), primary_key=True)
    provider_request: Mapped[ProviderRequest] = relationship(back_populates="items")
    request_item: Mapped[RequestItem] = relationship()


class EmailSend(Base):
    __tablename__ = "correo_envio"
    id: Mapped[int] = mapped_column(primary_key=True)
    provider_request_id: Mapped[int] = mapped_column(ForeignKey("solicitud_proveedor.id"), index=True)
    to_email: Mapped[str] = mapped_column(String(200))
    subject: Mapped[str] = mapped_column(String(250))
    body_text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="BORRADOR")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_request: Mapped[ProviderRequest] = relationship()


class Quote(Base):
    __tablename__ = "proforma"
    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("solicitud.id"), index=True)
    provider_id: Mapped[int | None] = mapped_column(ForeignKey("proveedor.id"), nullable=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    raw_text_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="PRELIMINAR")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    provider: Mapped[Provider | None] = relationship()
    details: Mapped[list[QuoteDetail]] = relationship(back_populates="quote", cascade="all, delete-orphan")


class QuoteDetail(Base):
    __tablename__ = "proforma_detalle"
    id: Mapped[int] = mapped_column(primary_key=True)
    quote_id: Mapped[int] = mapped_column(ForeignKey("proforma.id"), index=True)
    product_service_id: Mapped[int | None] = mapped_column(ForeignKey("producto_servicio.id"), nullable=True)
    description: Mapped[str] = mapped_column(String(300))
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    total_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    features_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    quote: Mapped[Quote] = relationship(back_populates="details")
    product_service: Mapped[ProductService | None] = relationship()
