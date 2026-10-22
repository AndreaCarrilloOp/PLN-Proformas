from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Iterable

import spacy
from spacy.matcher import PhraseMatcher
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.domain import Brand, LexicalVariant, ProductService

NUMBER_WORDS = {
    "un": 1, "uno": 1, "una": 1,
    "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
    "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
    "once": 11, "doce": 12, "trece": 13, "catorce": 14, "quince": 15,
    "dieciseis": 16, "dieciséis": 16, "diecisiete": 17, "dieciocho": 18,
    "diecinueve": 19, "veinte": 20,
}
NUMBER_PATTERN = "|".join(sorted(NUMBER_WORDS, key=len, reverse=True))


@dataclass
class NLPTransformation:
    field_name: str
    original_value: str
    normalized_value: str | None
    source: str
    confirmed: bool = True
    resolved: bool = True
    note: str | None = None


@dataclass
class ExtractedCharacteristic:
    key: str
    original: str
    normalized: str
    source: str


@dataclass
class ExtractedItem:
    fragment: str
    product_name: str | None = None
    product_id: int | None = None
    quantity: int | None = None
    unit_symbol: str | None = None
    brand_name: str | None = None
    brand_id: int | None = None
    characteristics: list[ExtractedCharacteristic] = field(default_factory=list)
    transformations: list[NLPTransformation] = field(default_factory=list)
    ambiguities: list[tuple[str, str]] = field(default_factory=list)


class NLPService:
    def __init__(self, db: Session | None = None):
        self.db = db
        try:
            self.nlp = spacy.load("es_core_news_sm")
        except OSError:
            self.nlp = spacy.blank("es")
        self.matcher = PhraseMatcher(self.nlp.vocab, attr="LOWER")
        self.products, self.variants, self.brands = self._catalog()
        patterns = [self.nlp.make_doc(v) for v in self.variants]
        self.matcher.add("PRODUCT_TERM", patterns)

    def _catalog(self):
        if self.db is not None:
            products = {p.name.lower(): (p.id, p.name) for p in self.db.scalars(select(ProductService).where(ProductService.active.is_(True))).all()}
            variants = {}
            for v in self.db.scalars(select(LexicalVariant)).all():
                product = self.db.get(ProductService, v.product_service_id) if v.product_service_id else None
                variants[v.variant.lower()] = {
                    "normalized": v.normalized_value,
                    "product_id": v.product_service_id,
                    "product_name": product.name if product else None,
                    "requires_confirmation": v.requires_confirmation,
                }
            brands = {b.name.lower(): (b.id, b.name) for b in self.db.scalars(select(Brand)).all()}
            if variants:
                return products, variants, brands
        return (
            {"laptop": (1, "Laptop"), "monitor": (2, "Monitor")},
            {
                "laptop": {"normalized": "Laptop", "product_id": 1, "product_name": "Laptop", "requires_confirmation": False},
                "laptops": {"normalized": "Laptop", "product_id": 1, "product_name": "Laptop", "requires_confirmation": False},
                "portátil": {"normalized": "Laptop", "product_id": 1, "product_name": "Laptop", "requires_confirmation": False},
                "portátiles": {"normalized": "Laptop", "product_id": 1, "product_name": "Laptop", "requires_confirmation": False},
                "computadora portátil": {"normalized": "Laptop", "product_id": 1, "product_name": "Laptop", "requires_confirmation": False},
                "monitor": {"normalized": "Monitor", "product_id": 2, "product_name": "Monitor", "requires_confirmation": False},
                "monitores": {"normalized": "Monitor", "product_id": 2, "product_name": "Monitor", "requires_confirmation": False},
                "compu": {"normalized": "computadora", "product_id": None, "product_name": None, "requires_confirmation": True},
                "compus": {"normalized": "computadora", "product_id": None, "product_name": None, "requires_confirmation": True},
                "computadora": {"normalized": "computadora", "product_id": None, "product_name": None, "requires_confirmation": True},
                "computadoras": {"normalized": "computadora", "product_id": None, "product_name": None, "requires_confirmation": True},
            },
            {"dell": (1, "Dell"), "lenovo": (2, "Lenovo"), "hp": (3, "HP"), "samsung": (4, "Samsung")},
        )

    def extract(self, text: str) -> list[ExtractedItem]:
        clean = " ".join(text.strip().split())
        mentions = self._product_mentions(clean)
        fragments = self._split_fragments(clean, mentions)
        if not fragments:
            fragments = [clean]
        return [self._extract_item(fragment) for fragment in fragments]

    def _product_mentions(self, text: str):
        doc = self.nlp.make_doc(text)
        mentions = []
        for _, start, end in self.matcher(doc):
            span = doc[start:end]
            cfg = self.variants.get(span.text.lower())
            if cfg:
                mentions.append((span.start_char, span.end_char, span.text, cfg))
        # Remove nested/overlapping shorter mentions, preferring longest.
        mentions.sort(key=lambda m: (m[0], -(m[1]-m[0])))
        filtered = []
        for m in mentions:
            if filtered and m[0] < filtered[-1][1]:
                continue
            filtered.append(m)
        # Una expresión es-CR como «compus portátiles» es un solo producto,
        # no dos artículos. La compatibilidad sigue dependiendo del catálogo.
        merged = []
        j = 0
        while j < len(filtered):
            current = filtered[j]
            if j + 1 < len(filtered):
                following = filtered[j + 1]
                between = text[current[1]:following[0]]
                if (current[2].lower() in {"compu", "compus", "computadora", "computadoras"}
                    and following[2].lower() in {"portátil", "portátiles"}
                    and not between.strip()):
                    merged.append((current[0], following[1], text[current[0]:following[1]],
                                   following[3]))
                    j += 2
                    continue
            merged.append(current)
            j += 1
        return merged

    def _split_fragments(self, text: str, mentions) -> list[str]:
        if len(mentions) <= 1:
            return [text] if text else []
        starts = []
        for idx, mention in enumerate(mentions):
            left = mentions[idx-1][1] if idx else 0
            prefix = text[left:mention[0]]
            qty_matches = list(re.finditer(rf"(?i)\b(?:\d+(?:[.,]\d+)?|{NUMBER_PATTERN})\b", prefix))
            if qty_matches:
                starts.append(left + qty_matches[-1].start())
            else:
                starts.append(mention[0])
        fragments = []
        for i, start in enumerate(starts):
            end = starts[i+1] if i+1 < len(starts) else len(text)
            frag = text[start:end].strip(" ,;y")
            if frag:
                fragments.append(frag)
        return fragments

    def _extract_item(self, fragment: str) -> ExtractedItem:
        item = ExtractedItem(fragment=fragment)
        mentions = self._product_mentions(fragment)
        if mentions:
            _, _, original, cfg = mentions[0]
            item.product_id = cfg["product_id"]
            item.product_name = cfg["product_name"]
            if original.lower() != str(cfg["normalized"]).lower() or cfg["requires_confirmation"]:
                item.transformations.append(NLPTransformation(
                    field_name="producto",
                    original_value=original,
                    normalized_value=cfg["normalized"],
                    source="VARIANTE_LEXICA",
                    confirmed=not cfg["requires_confirmation"],
                    resolved=not cfg["requires_confirmation"],
                    note="La expresión requiere aclarar si se trata de computadora portátil o de escritorio." if cfg["requires_confirmation"] else None,
                ))
            if cfg["requires_confirmation"]:
                item.ambiguities.append(("producto", "¿La computadora requerida es portátil o de escritorio?"))
        item.quantity = self._quantity(fragment, mentions[0][0] if mentions else None)
        item.unit_symbol = self._unit(fragment)
        self._brand(fragment, item)
        item.characteristics.extend(self._characteristics(fragment))
        return item

    def _quantity(self, fragment: str, product_start: int | None) -> int | None:
        scope = fragment[:product_start] if product_start is not None else fragment
        matches = list(re.finditer(rf"(?i)\b(\d+(?:[.,]\d+)?|{NUMBER_PATTERN})\b", scope))
        if not matches:
            matches = list(re.finditer(rf"(?i)\b(\d+(?:[.,]\d+)?|{NUMBER_PATTERN})\b", fragment))
        if not matches:
            return None
        raw = matches[-1].group(1).lower()
        if raw in NUMBER_WORDS:
            return NUMBER_WORDS[raw]
        try:
            return int(float(raw.replace(",", ".")))
        except ValueError:
            return None

    def _unit(self, fragment: str) -> str:
        """Distingue la unidad comercial explícita de atributos técnicos como GB."""
        pattern = rf"(?i)\\b(?:\\d+(?:[.,]\\d+)?|{NUMBER_PATTERN})\\s+(cajas?|resmas?|paquetes?|unidades?|servicios?)\\b"
        match = re.search(pattern, fragment)
        if not match:
            return "unidad"
        token = match.group(1).lower()
        if token.startswith("caja"):
            return "caja"
        if token.startswith("resma"):
            return "resma"
        if token.startswith("paquete"):
            return "paquete"
        if token.startswith("servicio"):
            return "servicio"
        return "unidad"

    @staticmethod
    def is_non_commercial(text: str, items: list[ExtractedItem]) -> bool:
        """Rechazo conservador: no reemplaza la aclaración de compras desconocidas."""
        if any(item.product_id is not None for item in items):
            return False
        # El verbo regional «ocupo» no convierte una búsqueda de empleo en compra.
        non_purchase = (
            r"\\b(?:ocupo|quiero|necesito|busco|solicito)\\s+"
            r"(?:(?:el|un|una|la)\\s+)?(?:puesto|empleo|trabajo|vacaciones)\\b",
            r"\\b(?:clima|pron[oó]stico\\s+del\\s+tiempo)\\b",
        )
        return any(re.search(pat, text, flags=re.I) for pat in non_purchase)

    def _brand(self, fragment: str, item: ExtractedItem) -> None:
        low = fragment.lower()
        for key, (bid, name) in self.brands.items():
            if re.search(rf"(?i)(?<!\w){re.escape(key)}(?!\w)", low):
                item.brand_id, item.brand_name = bid, name
                return
        tokens = re.findall(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+", fragment)
        best = None
        for token in tokens:
            t = token.lower()
            if len(t) < 4:
                continue
            for key, (bid, name) in self.brands.items():
                score = SequenceMatcher(None, t, key).ratio()
                if score >= 0.72 and t != key and (best is None or score > best[0]):
                    best = (score, token, bid, name)
        if best:
            _, original, bid, name = best
            item.transformations.append(NLPTransformation(
                field_name="marca",
                original_value=original,
                normalized_value=name,
                source="COINCIDENCIA_APROXIMADA",
                confirmed=False,
                resolved=False,
                note=f"¿Quiso indicar {name}?",
            ))

    def _characteristics(self, fragment: str) -> list[ExtractedCharacteristic]:
        out = []
        seen = set()
        # Colores explícitos del artículo; nunca se transfieren al artículo siguiente.
        color = re.search(r"(?i)\b(blanc[oa]s?|negr[oa]s?|azul(?:es)?|roj[oa]s?|verd(?:e|es))\b", fragment)
        if color:
            original_color = color.group(1).lower()
            normalized_color = (
                "blanco" if original_color.startswith("blanc") else
                "negro" if original_color.startswith("negr") else
                "azul" if original_color.startswith("azul") else
                "rojo" if original_color.startswith("roj") else
                "verde"
            )
            out.append(ExtractedCharacteristic("color", color.group(0),
                                               normalized_color, "REGEX"))
            seen.add("color")
        processor = re.search(r"(?i)\b(?:intel\s+core\s+)?i([3579])\b", fragment)
        if processor:
            normalized = f"Intel Core i{processor.group(1)}"
            out.append(ExtractedCharacteristic("procesador", processor.group(0), normalized, "REGEX")); seen.add("procesador")
        ram = re.search(r"(?i)\b(\d+)\s*(GB|TB)\s*(?:de\s*)?(?:RAM|memoria)\b|\b(?:RAM|memoria)\s*(?:de\s*)?(\d+)\s*(GB|TB)\b", fragment)
        if ram:
            amount = ram.group(1) or ram.group(3); unit = (ram.group(2) or ram.group(4)).upper()
            out.append(ExtractedCharacteristic("ram", ram.group(0), f"{amount} {unit}", "REGEX")); seen.add("ram")
        storage = re.search(r"(?i)\b(\d+)\s*(GB|TB)\s*(SSD|HDD)\b", fragment)
        if storage:
            out.append(ExtractedCharacteristic("almacenamiento", storage.group(0), f"{storage.group(1)} {storage.group(2).upper()} {storage.group(3).upper()}", "REGEX")); seen.add("almacenamiento")
        screen = re.search(r"(?i)\b(\d+(?:[.,]\d+)?)\s*(?:pulgadas?|\")", fragment)
        if screen:
            value = screen.group(1).replace(",", ".")
            out.append(ExtractedCharacteristic("tamano_pantalla", screen.group(0), f"{value} pulgadas", "REGEX")); seen.add("tamano_pantalla")
        return out
