from __future__ import annotations

import os
import re
import tempfile
from decimal import Decimal
from pathlib import Path

import pdfplumber
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.domain import ProductService, Provider, Quote, QuoteDetail, Request


class PDFService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def process_upload(self, request_id: int, provider_id: int | None, filename: str, content: bytes) -> Quote:
        if Path(filename).suffix.lower() != ".pdf":
            raise ValueError("El archivo debe tener extensión PDF")
        if len(content) > self.settings.max_pdf_mb * 1024 * 1024:
            raise ValueError(f"El PDF supera el límite de {self.settings.max_pdf_mb} MB")
        if not content.startswith(b"%PDF"):
            raise ValueError("El archivo no contiene una firma PDF válida")
        if not self.db.get(Request, request_id):
            raise ValueError("Solicitud no encontrada")
        if provider_id is not None and not self.db.get(Provider, provider_id):
            raise ValueError("Proveedor no encontrado")
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(content); temp_path = tmp.name
            text = self._extract_text(temp_path)
            if not text.strip():
                raise ValueError("El PDF no contiene texto seleccionable; no se utiliza OCR")
            if provider_id is None and text:
                provider_id = self._detect_provider(text)
            quote = Quote(request_id=request_id, provider_id=provider_id, original_filename=Path(filename).name, raw_text_excerpt=text[:5000] if text else None, status="PRELIMINAR")
            self.db.add(quote); self.db.flush()
            if text:
                self._extract_details(quote, text)
            self.db.commit(); self.db.refresh(quote)
            return quote
        finally:
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)

    def _extract_text(self, path: str) -> str:
        parts = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                value = page.extract_text() or ""
                if value.strip():
                    parts.append(value)
        return "\n".join(parts).strip()

    def _detect_provider(self, text: str) -> int | None:
        low = text.lower()
        for provider in self.db.scalars(select(Provider).where(Provider.active.is_(True))).all():
            if provider.name.lower() in low:
                return provider.id
        return None

    def _extract_details(self, quote: Quote, text: str) -> None:
        products = self.db.scalars(select(ProductService)).all()
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        for product in products:
            matching = next((line for line in lines if product.name.lower() in line.lower() or (product.name == "Laptop" and "laptop" in line.lower()) or (product.name == "Monitor" and "monitor" in line.lower())), None)
            if not matching:
                continue
            qty = None
            qty_match = re.search(r"(?i)\b(?:cant(?:idad)?[:\s]*)?(\d+(?:[.,]\d+)?)\b", matching)
            if qty_match:
                try: qty = Decimal(qty_match.group(1).replace(",", "."))
                except Exception: pass
            prices = re.findall(r"(?:₡|\$|CRC\s*|USD\s*)\s*([\d.,]+)", matching, flags=re.I)
            price = None
            if prices:
                raw = prices[-1].replace(" ", "")
                if raw.count(",") == 1 and raw.count(".") == 0:
                    raw = raw.replace(",", ".")
                else:
                    raw = raw.replace(",", "")
                try: price = Decimal(raw)
                except Exception: pass
            self.db.add(QuoteDetail(quote_id=quote.id, product_service_id=product.id, description=matching[:300], quantity=qty, unit_price=price, total_price=(qty * price if qty is not None and price is not None else None), features_text=matching[:1000], confirmed=False))

    def validate(self, quote_id: int, provider_id: int | None, details: list[dict]) -> Quote:
        quote = self.db.get(Quote, quote_id)
        if not quote:
            raise ValueError("Proforma no encontrada")
        if provider_id is not None:
            if not self.db.get(Provider, provider_id):
                raise ValueError("Proveedor no encontrado")
            quote.provider_id = provider_id
        quote.details.clear(); self.db.flush()
        for d in details:
            quote.details.append(QuoteDetail(
                product_service_id=d.get("producto_servicio_id"),
                description=d["descripcion"],
                quantity=d.get("cantidad"), unit_price=d.get("precio_unitario"), total_price=d.get("precio_total"),
                features_text=d.get("caracteristicas"), confirmed=True,
            ))
        quote.status = "VALIDADA"
        self.db.commit(); self.db.refresh(quote)
        return quote
