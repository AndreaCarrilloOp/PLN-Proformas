from pydantic import BaseModel, Field


class EmailUpdate(BaseModel):
    destinatario: str = Field(min_length=3, max_length=200)
    asunto: str = Field(min_length=1, max_length=250)
    contenido: str = Field(min_length=1, max_length=20000)
