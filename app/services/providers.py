from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.domain import Provider, ProviderProductService, ProviderRequest, ProviderRequestItem, Request


class ProviderService:
    def __init__(self, db: Session):
        self.db = db

    def generate_for_request(self, request_id: int) -> list[ProviderRequest]:
        req = self.db.get(Request, request_id)
        if not req:
            raise ValueError("Solicitud no encontrada")
        if req.status != "COMPLETO":
            raise ValueError("Todos los artículos deben estar completos antes de generar solicitudes por proveedor")

        providers = self.db.scalars(select(Provider).where(Provider.active.is_(True))).all()
        created: list[ProviderRequest] = []

        for provider in providers:
            supported = set(
                self.db.scalars(
                    select(ProviderProductService.product_service_id).where(
                        ProviderProductService.provider_id == provider.id
                    )
                ).all()
            )
            matching_items = [item for item in req.items if item.product_service_id in supported]
            if not matching_items:
                continue

            pr = self.db.scalar(
                select(ProviderRequest).where(
                    ProviderRequest.request_id == request_id,
                    ProviderRequest.provider_id == provider.id,
                )
            )
            if not pr:
                pr = ProviderRequest(request_id=request_id, provider_id=provider.id, status="BORRADOR")
                self.db.add(pr)
                self.db.flush()

            # Sincroniza la solicitud por proveedor con la relación actual del catálogo.
            # Así nunca se conserva accidentalmente un artículo que el proveedor ya no ofrece.
            matching_ids = {item.id for item in matching_items}
            pr.items[:] = [row for row in pr.items if row.request_item_id in matching_ids]
            existing_ids = {row.request_item_id for row in pr.items}
            for item in matching_items:
                if item.id not in existing_ids:
                    pr.items.append(ProviderRequestItem(request_item_id=item.id))

            created.append(pr)

        self.db.commit()
        return created

    def serialize(self, prs: list[ProviderRequest]) -> list[dict]:
        rows: list[dict] = []
        for pr in prs:
            request = self.db.get(Request, pr.request_id)
            request_items = list(request.items) if request else []
            included_ids = {row.request_item_id for row in pr.items}
            omitted = [item for item in request_items if item.id not in included_ids]
            total = len(request_items)
            included = len(pr.items)

            rows.append({
                "id": pr.id,
                "solicitud_id": pr.request_id,
                "proveedor": pr.provider.name,
                "email": pr.provider.email,
                "estado": pr.status,
                "cobertura": "TOTAL" if total and included == total else "PARCIAL",
                "articulos_incluidos": included,
                "articulos_totales": total,
                "articulos": [{
                    "articulo_id": row.request_item.id,
                    "producto": row.request_item.product_service.name if row.request_item.product_service else None,
                    "cantidad": row.request_item.quantity,
                } for row in pr.items],
                "articulos_no_incluidos": [{
                    "articulo_id": item.id,
                    "producto": item.product_service.name if item.product_service else None,
                    "cantidad": item.quantity,
                } for item in omitted],
            })
        return rows
