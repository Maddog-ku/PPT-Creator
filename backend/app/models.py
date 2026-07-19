import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class PresentationStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PARSING = "PARSING"
    GENERATING_CONTENT = "GENERATING_CONTENT"
    RENDERING = "RENDERING"
    PREVIEW_READY = "PREVIEW_READY"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Presentation(Base):
    __tablename__ = "presentations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    language: Mapped[str] = mapped_column(String(16), nullable=False, default="zh-TW")
    status: Mapped[PresentationStatus] = mapped_column(
        Enum(PresentationStatus, name="presentation_status"),
        nullable=False,
        default=PresentationStatus.DRAFT,
        index=True,
    )
    source_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    outline: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    content: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
