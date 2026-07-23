import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base
from .job_timing import estimate_job_duration_seconds, estimate_job_remaining_seconds


class PresentationStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PARSING = "PARSING"
    GENERATING_CONTENT = "GENERATING_CONTENT"
    RENDERING = "RENDERING"
    PREVIEW_READY = "PREVIEW_READY"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class AIProviderConfig(Base):
    __tablename__ = "ai_provider_configs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    model: Mapped[str] = mapped_column(String(180), nullable=False)
    image_model: Mapped[str | None] = mapped_column(String(180), nullable=True)
    encrypted_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    @property
    def has_api_key(self) -> bool:
        return bool(self.encrypted_api_key)


class Presentation(Base):
    __tablename__ = "presentations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    language: Mapped[str] = mapped_column(String(16), nullable=False, default="zh-TW")
    template: Mapped[str] = mapped_column(String(40), nullable=False, default="editorial")
    status: Mapped[PresentationStatus] = mapped_column(
        Enum(PresentationStatus, name="presentation_status"),
        nullable=False,
        default=PresentationStatus.DRAFT,
        index=True,
    )
    source_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    outline: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    content: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    generation_settings: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    failed_stage: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_rendered_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    @property
    def slide_count(self) -> int:
        slides = (self.content or {}).get("slides", [])
        return len(slides) if isinstance(slides, list) else 0


class PresentationVersion(Base):
    __tablename__ = "presentation_versions"
    __table_args__ = (
        UniqueConstraint(
            "presentation_id",
            "revision",
            name="uq_presentation_versions_presentation_revision",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    presentation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("presentations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    language: Mapped[str] = mapped_column(String(16), nullable=False)
    template: Mapped[str] = mapped_column(String(40), nullable=False)
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    change_reason: Mapped[str] = mapped_column(
        String(80), nullable=False, default="content_saved"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class GenerationJob(Base):
    __tablename__ = "generation_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    presentation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("presentations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="QUEUED", index=True
    )
    stage: Mapped[str] = mapped_column(String(40), nullable=False, default="queued")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cancel_requested: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    @property
    def estimated_duration_seconds(self) -> int:
        return estimate_job_duration_seconds(self.job_type, self.payload)

    @property
    def estimated_remaining_seconds(self) -> int:
        return estimate_job_remaining_seconds(
            job_type=self.job_type,
            payload=self.payload,
            status=self.status,
            progress=self.progress,
            started_at=self.started_at,
        )
