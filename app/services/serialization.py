from app.models.domain import Request


def request_to_dict(req: Request) -> dict:
    return {
        "id": req.id,
        "texto_original": req.original_text,
        "estado": req.status,
        "articulos": [
            {
                "id": item.id,
                "fragmento_original": item.original_fragment,
                "producto": item.product_service.name if item.product_service else None,
                "cantidad": item.quantity,
                "marca": item.brand.name if item.brand else None,
                "estado": item.status,
                "caracteristicas": [
                    {
                        "key": c.characteristic.key,
                        "name": c.characteristic.name,
                        "original_value": c.original_value,
                        "normalized_value": c.normalized_value,
                        "source": c.source,
                        "confirmed": c.confirmed,
                    } for c in item.characteristics
                ],
                "preguntas": [
                    {"id": q.id, "field_key": q.field_key, "question_text": q.question_text, "status": q.status}
                    for q in item.questions
                ],
                "transformaciones": [
                    {
                        "id": t.id, "field_name": t.field_name, "original_value": t.original_value,
                        "normalized_value": t.normalized_value, "source": t.source,
                        "confirmed": t.confirmed, "resolved": t.resolved, "note": t.note,
                    } for t in item.transformations
                ],
            } for item in req.items
        ],
    }
