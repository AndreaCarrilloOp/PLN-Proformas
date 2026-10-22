from decimal import Decimal

from pydantic import BaseModel, Field


class RequestCreate(BaseModel):
    texto: str = Field(min_length=3, max_length=5000)


class AnswerCreate(BaseModel):
    pregunta_id: int
    respuesta: str = Field(min_length=1, max_length=500)


class ConfirmationCreate(BaseModel):
    transformacion_id: int
    confirmado: bool
    valor_corregido: str | None = Field(default=None, max_length=200)


class CharacteristicOut(BaseModel):
    key: str
    name: str
    original_value: str
    normalized_value: str
    source: str
    confirmed: bool


class QuestionOut(BaseModel):
    id: int
    field_key: str
    question_text: str
    status: str


class TransformationOut(BaseModel):
    id: int
    field_name: str
    original_value: str
    normalized_value: str | None
    source: str
    confirmed: bool
    resolved: bool
    note: str | None


class ItemOut(BaseModel):
    id: int
    fragmento_original: str
    producto: str | None
    cantidad: Decimal | None
    marca: str | None
    estado: str
    caracteristicas: list[CharacteristicOut]
    preguntas: list[QuestionOut]
    transformaciones: list[TransformationOut]


class RequestOut(BaseModel):
    id: int
    texto_original: str
    estado: str
    articulos: list[ItemOut]
