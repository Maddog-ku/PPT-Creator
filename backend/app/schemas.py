import uuid
from datetime import datetime
from html import unescape
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import PresentationStatus


AIProviderType = Literal[
    "ollama",
    "openai",
    "anthropic",
    "gemini",
    "openai_compatible",
]


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


class SlideContent(BaseModel):
    eyebrow: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=400)
    kind: Literal["cover", "cards", "metric", "roadmap", "closing"]

    @field_validator("eyebrow", "title", "body", mode="before")
    @classmethod
    def normalize_plain_text(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        plain = re.sub(r"<[^>]+>", " ", value)
        return " ".join(unescape(plain).split())


class GeneratedDeck(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    language: str = Field(min_length=2, max_length=16)
    slides: list[SlideContent] = Field(min_length=3, max_length=20)


class GenerationRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=1500)
    language: str = Field(default="zh-TW", max_length=16)
    slide_count: int = Field(default=10, ge=3, le=20)
    template: str = Field(default="editorial", max_length=40)
    source_text: str | None = Field(default=None, max_length=60_000)
    provider_id: uuid.UUID | None = None


class GenerationResponse(GeneratedDeck):
    provider: str
    model: str


class AIProviderRead(BaseModel):
    provider: str
    model: str
    transport: Literal["api"] = "api"


class AIProviderConfigCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    provider: AIProviderType
    base_url: str = Field(min_length=8, max_length=500)
    model: str = Field(min_length=1, max_length=180)
    api_key: str | None = Field(default=None, max_length=5_000)


class AIProviderConfigUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    provider: AIProviderType | None = None
    base_url: str | None = Field(default=None, min_length=8, max_length=500)
    model: str | None = Field(default=None, min_length=1, max_length=180)
    api_key: str | None = Field(default=None, max_length=5_000)


class AIProviderConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    provider: str
    base_url: str
    model: str
    has_api_key: bool
    created_at: datetime
    updated_at: datetime


class AIProviderConnectionRead(BaseModel):
    connected: bool
    provider: str
    model: str
    available_models: list[str]
    error: str | None = None


class OllamaModelRead(BaseModel):
    name: str
    size: int | None = None
    parameter_size: str | None = None
    quantization_level: str | None = None


class OllamaConnectionRead(BaseModel):
    connected: bool
    provider: Literal["ollama"] = "ollama"
    base_url: str
    configured_model: str
    available_models: list[str]
    error: str | None = None
