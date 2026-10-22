from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.domain import (
    Brand,
    Characteristic,
    ItemCharacteristic,
    ProductService,
    Request,
    RequestItem,
    RequirementTemplate,
    UnitMeasure,
    Transformation,
    ValidationQuestion,
    ValidationResponse,
)
from app.services.nlp import NLPService


class RequestService:
    def __init__(self, db: Session):
        self.db = db

    def create(self, text: str, owner_user_id: int) -> Request:
        req = Request(original_text=text, owner_user_id=owner_user_id, status="PENDIENTE")
        self.db.add(req)
        self.db.flush()
        service = NLPService(self.db)
        extracted = service.extract(text)
        if service.is_non_commercial(text, extracted):
            self.db.rollback()
            raise ValueError("El texto no describe una solicitud comercial de bienes o servicios")
        for ext in extracted:
            product = self._resolve_product(ext.product_id, ext.product_name)
            brand = self._resolve_brand(ext.brand_id, ext.brand_name)
            item = RequestItem(
                request_id=req.id,
                product_service_id=product.id if product else None,
                original_fragment=ext.fragment,
                quantity=Decimal(ext.quantity) if ext.quantity is not None else None,
                unit_measure_id=self.db.scalar(select(UnitMeasure.id).where(UnitMeasure.symbol == (ext.unit_symbol or "unidad"))),
                brand_id=brand.id if brand else None,
                status="PENDIENTE",
            )
            self.db.add(item); self.db.flush()
            for c in ext.characteristics:
                characteristic = self.db.scalar(select(Characteristic).where(Characteristic.key == c.key))
                if characteristic:
                    self.db.add(ItemCharacteristic(
                        request_item_id=item.id,
                        characteristic_id=characteristic.id,
                        original_value=c.original,
                        normalized_value=c.normalized,
                        source=c.source,
                        confirmed=True,
                    ))
            for t in ext.transformations:
                self.db.add(Transformation(
                    request_item_id=item.id,
                    field_name=t.field_name,
                    original_value=t.original_value,
                    normalized_value=t.normalized_value,
                    source=t.source,
                    confirmed=t.confirmed,
                    resolved=t.resolved,
                    note=t.note,
                ))
            for key, question in ext.ambiguities:
                self.db.add(ValidationQuestion(request_item_id=item.id, field_key=key, question_text=question, status="PENDIENTE"))
            self.db.flush()
            self._add_missing_questions(item)
            self._recalculate_item(item)
        self._recalculate_request(req)
        self.db.commit(); self.db.refresh(req)
        return req

    def _resolve_product(self, product_id, product_name):
        if product_id:
            obj = self.db.get(ProductService, product_id)
            if obj:
                return obj
        if product_name:
            return self.db.scalar(select(ProductService).where(ProductService.name.ilike(product_name)))
        return None

    def _resolve_brand(self, brand_id, brand_name):
        if brand_id:
            obj = self.db.get(Brand, brand_id)
            if obj:
                return obj
        if brand_name:
            return self.db.scalar(select(Brand).where(Brand.name.ilike(brand_name)))
        return None

    def _add_missing_questions(self, item: RequestItem) -> None:
        existing_keys = {q.field_key for q in item.questions if q.status == "PENDIENTE"}
        if item.product_service_id is None and "producto" not in existing_keys:
            item.questions.append(ValidationQuestion(field_key="producto", question_text="¿Qué producto o servicio necesita?", status="PENDIENTE"))
        if item.quantity is None and "cantidad" not in existing_keys:
            item.questions.append(ValidationQuestion(field_key="cantidad", question_text="¿Qué cantidad necesita?", status="PENDIENTE"))
        if not item.product_service_id:
            return
        template = self.db.scalar(select(RequirementTemplate).where(RequirementTemplate.product_service_id == item.product_service_id, RequirementTemplate.active.is_(True)))
        if not template:
            return
        present = {c.characteristic.key for c in item.characteristics}
        for field in template.fields:
            if field.required and field.characteristic.key not in present and field.characteristic.key not in existing_keys:
                item.questions.append(ValidationQuestion(field_key=field.characteristic.key, question_text=field.question_text, status="PENDIENTE"))

    def answer(self, request_id: int, question_id: int, answer: str) -> Request:
        req = self.db.get(Request, request_id)
        if not req:
            raise ValueError("Solicitud no encontrada")
        question = self.db.get(ValidationQuestion, question_id)
        if not question or question.request_item_id not in {i.id for i in req.items}:
            raise ValueError("Pregunta no encontrada para esta solicitud")
        item = question.item
        if question.status != "PENDIENTE":
            raise ValueError("La pregunta ya fue respondida")
        normalized = answer.strip()
        if not normalized:
            raise ValueError("La respuesta no puede quedar vacía")
        self.db.add(ValidationResponse(question_id=question.id, response_text=answer, normalized_value=normalized))
        if question.field_key == "cantidad":
            try:
                item.quantity = Decimal(normalized.replace(",", "."))
            except Exception as exc:
                raise ValueError("La cantidad debe ser numérica") from exc
        elif question.field_key == "producto":
            low = normalized.lower()
            if "port" in low or "laptop" in low:
                product = self.db.scalar(select(ProductService).where(ProductService.name == "Laptop"))
            elif "monitor" in low:
                product = self.db.scalar(select(ProductService).where(ProductService.name == "Monitor"))
            else:
                product = self.db.scalar(select(ProductService).where(ProductService.name.ilike(normalized)))
            if not product:
                raise ValueError("Producto no reconocido dentro del catálogo controlado")
            item.product_service_id = product.id
            # La respuesta humana resuelve las normalizaciones léxicas ambiguas del producto.
            for transformation in item.transformations:
                if transformation.field_name == "producto" and not transformation.confirmed:
                    transformation.confirmed = True
                    transformation.resolved = True
                    transformation.note = (transformation.note or "") + f" Resuelto por el usuario como {product.name}."
        elif question.field_key == "marca":
            brand = self.db.scalar(select(Brand).where(Brand.name.ilike(normalized)))
            if not brand:
                raise ValueError("Marca no reconocida dentro del catálogo")
            item.brand_id = brand.id
        else:
            characteristic = self.db.scalar(select(Characteristic).where(Characteristic.key == question.field_key))
            if not characteristic:
                raise ValueError("Campo de plantilla no reconocido")
            # Reconoce varios atributos dentro de una misma respuesta, pero solo
            # completa campos que pertenecen a la plantilla del artículo.
            template = self.db.scalar(select(RequirementTemplate).where(
                RequirementTemplate.product_service_id == item.product_service_id,
                RequirementTemplate.active.is_(True)))
            allowed = {field.characteristic.key for field in template.fields} if template else set()
            extracted = {
                part.key: part for part in NLPService(self.db)._characteristics(normalized)
                if part.key in allowed
            }
            if question.field_key not in extracted and extracted:
                raise ValueError("La respuesta no contiene el atributo solicitado")
            for key, part in extracted.items():
                definition = self.db.scalar(select(Characteristic).where(Characteristic.key == key))
                if not definition:
                    continue
                current = self.db.scalar(select(ItemCharacteristic).where(
                    ItemCharacteristic.request_item_id == item.id,
                    ItemCharacteristic.characteristic_id == definition.id))
                if current is None:
                    self.db.add(ItemCharacteristic(
                        request_item_id=item.id, characteristic_id=definition.id,
                        original_value=part.original, normalized_value=part.normalized,
                        source="RESPUESTA_USUARIO", confirmed=True))
                else:
                    current.original_value = part.original
                    current.normalized_value = part.normalized
                    current.source = "RESPUESTA_USUARIO"
                    current.confirmed = True
                for pending in item.questions:
                    if pending.field_key == key and pending.status == "PENDIENTE":
                        pending.status = "RESPONDIDA"
                        if pending.id != question.id:
                            self.db.add(ValidationResponse(
                                question_id=pending.id, response_text=answer,
                                normalized_value=part.normalized))
            if not extracted:
                # Valores libres permanecen disponibles para revisión humana.
                current = self.db.scalar(select(ItemCharacteristic).where(
                    ItemCharacteristic.request_item_id == item.id,
                    ItemCharacteristic.characteristic_id == characteristic.id))
                if current is None:
                    self.db.add(ItemCharacteristic(
                        request_item_id=item.id, characteristic_id=characteristic.id,
                        original_value=answer, normalized_value=normalized,
                        source="RESPUESTA_USUARIO", confirmed=True))
                else:
                    current.original_value = answer
                    current.normalized_value = normalized
                    current.source = "RESPUESTA_USUARIO"
                    current.confirmed = True
        question.status = "RESPONDIDA"
        self.db.flush()
        self._add_missing_questions(item)
        self._recalculate_item(item); self._recalculate_request(req)
        self.db.commit(); self.db.refresh(req)
        return req

    def confirm(self, request_id: int, transformation_id: int, confirmed: bool, corrected_value: str | None = None) -> Request:
        req = self.db.get(Request, request_id)
        if not req:
            raise ValueError("Solicitud no encontrada")
        trans = self.db.get(Transformation, transformation_id)
        if not trans or not trans.item or trans.item.request_id != request_id:
            raise ValueError("Transformación no encontrada para esta solicitud")
        trans.confirmed = confirmed
        trans.resolved = True
        if corrected_value:
            trans.normalized_value = corrected_value
            trans.note = (trans.note or "") + " Valor corregido manualmente por el usuario."
        item = trans.item
        if confirmed or corrected_value:
            if trans.field_name == "marca" and trans.normalized_value:
                brand = self.db.scalar(select(Brand).where(Brand.name.ilike(trans.normalized_value)))
                if brand:
                    item.brand_id = brand.id
            elif trans.field_name == "producto" and trans.normalized_value:
                if trans.normalized_value.lower() == "computadora":
                    # "computadora" sigue siendo ambigua; requiere respuesta de producto.
                    pass
                else:
                    product = self.db.scalar(select(ProductService).where(ProductService.name.ilike(trans.normalized_value)))
                    if product:
                        item.product_service_id = product.id
        self._recalculate_item(item); self._recalculate_request(req)
        self.db.commit(); self.db.refresh(req)
        return req

    def _recalculate_item(self, item: RequestItem) -> None:
        pending = [q for q in item.questions if q.status == "PENDIENTE"]
        unresolved = [t for t in item.transformations if not t.resolved]
        if unresolved:
            item.status = "REQUIERE_CONFIRMACION"
        elif item.product_service_id and item.quantity is not None and not pending:
            item.status = "COMPLETO"
        else:
            item.status = "PENDIENTE"

    def _recalculate_request(self, req: Request) -> None:
        statuses = {i.status for i in req.items}
        req.status = "COMPLETO" if statuses and statuses == {"COMPLETO"} else ("REQUIERE_CONFIRMACION" if "REQUIERE_CONFIRMACION" in statuses else "PENDIENTE")
