import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .models import PresentationStatus


class PresentationCreate(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    language: str = Field(default="zh-TW", max_length=16)
    source_text: str | None = Field(default=None, max_length=20_000)


class PresentationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    language: str
    status: PresentationStatus
    confirmed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class HealthRead(BaseModel):
    status: str
    database: str
