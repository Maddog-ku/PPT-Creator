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
    "stable_diffusion",
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
    template: str = "editorial"
    status: PresentationStatus
    confirmed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    slide_count: int = 0
    has_output: bool = False
    revision: int = 1
    last_rendered_revision: int | None = None
    has_unrendered_changes: bool = False
    failed_stage: str | None = None
    last_error: str | None = None
    can_retry: bool = False


class PresentationBatchDelete(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=100)


class PresentationDeleteResult(BaseModel):
    deleted: int


class HealthRead(BaseModel):
    status: str
    database: str


class SlideContent(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    eyebrow: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=400)
    kind: Literal[
        "cover",
        "section",
        "cards",
        "split",
        "metric",
        "comparison",
        "roadmap",
        "quote",
        "closing",
    ]
    visual_prompt: str | None = Field(default=None, max_length=500)
    image_data: str | None = None

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
    slides: list[SlideContent] = Field(min_length=3, max_length=50)


class OutlineItem(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    eyebrow: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=120)
    objective: str = Field(min_length=1, max_length=300)
    kind: Literal[
        "cover",
        "section",
        "cards",
        "split",
        "metric",
        "comparison",
        "roadmap",
        "quote",
        "closing",
    ]

    @field_validator("eyebrow", "title", "objective", mode="before")
    @classmethod
    def normalize_outline_text(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        plain = re.sub(r"<[^>]+>", " ", value)
        return " ".join(unescape(plain).split())


class PresentationOutline(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    language: str = Field(min_length=2, max_length=16)
    items: list[OutlineItem] = Field(min_length=3, max_length=50)


class PresentationOutlineUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    language: str = Field(min_length=2, max_length=16)
    items: list[OutlineItem] = Field(min_length=3, max_length=50)


class PresentationVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    revision: int
    title: str
    language: str
    template: str
    change_reason: str
    created_at: datetime
    slide_count: int = 0


class PresentationVersionDetailRead(PresentationVersionRead):
    content: GeneratedDeck


class PresentationDetailRead(PresentationRead):
    content: GeneratedDeck | None = None
    outline: PresentationOutline | None = None
    preview_urls: list[str] = Field(default_factory=list)
    pptx_url: str | None = None
    pdf_url: str | None = None


class PresentationContentUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    language: str = Field(default="zh-TW", max_length=16)
    slides: list[SlideContent] = Field(min_length=3, max_length=50)


class SourceExtractionItem(BaseModel):
    filename: str
    status: Literal["success", "error"]
    text: str = ""
    char_count: int = 0
    error: str | None = None


class SourceExtractionResponse(BaseModel):
    files: list[SourceExtractionItem] = Field(default_factory=list)
    combined_text: str = ""


class PresentationRenderRead(BaseModel):
    presentation_id: uuid.UUID
    slide_count: int
    preview_urls: list[str]
    pptx_url: str
    pdf_url: str


class GenerationRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=1500)
    language: str = Field(default="zh-TW", max_length=16)
    slide_count: int = Field(default=10, ge=3, le=50)
    template: str = Field(default="editorial", max_length=40)
    source_text: str | None = Field(default=None, max_length=60_000)
    provider_id: uuid.UUID | None = None
    generate_images: bool = False
    image_provider_id: uuid.UUID | None = None
    image_count: int = Field(default=2, ge=1, le=3)


class GenerationResponse(GeneratedDeck):
    provider: str
    model: str
    presentation_id: uuid.UUID | None = None


class GenerationJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    presentation_id: uuid.UUID
    job_type: Literal["outline", "content"]
    status: Literal["QUEUED", "RUNNING", "COMPLETED", "FAILED", "CANCELED"]
    stage: str
    progress: int
    cancel_requested: bool
    error: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    updated_at: datetime


class GenerationJobCreated(BaseModel):
    presentation_id: uuid.UUID
    job: GenerationJobRead


class GenerationJobSummaryRead(GenerationJobRead):
    presentation_title: str
    presentation_status: PresentationStatus
    can_retry: bool


class AIProviderRead(BaseModel):
    provider: str
    model: str
    image_model: str | None = None
    transport: Literal["api"] = "api"


class AIProviderConfigCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    provider: AIProviderType
    base_url: str = Field(min_length=8, max_length=500)
    model: str = Field(min_length=1, max_length=180)
    image_model: str | None = Field(default=None, max_length=180)
    api_key: str | None = Field(default=None, max_length=5_000)


class AIProviderConfigUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    provider: AIProviderType | None = None
    base_url: str | None = Field(default=None, min_length=8, max_length=500)
    model: str | None = Field(default=None, min_length=1, max_length=180)
    image_model: str | None = Field(default=None, max_length=180)
    api_key: str | None = Field(default=None, max_length=5_000)


class AIProviderConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    provider: str
    base_url: str
    model: str
    image_model: str | None
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
