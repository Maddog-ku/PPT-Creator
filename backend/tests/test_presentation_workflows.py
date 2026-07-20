import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.main import (
    _duplicate_deck,
    _ensure_presentation_downloadable,
    _presentation_read,
)
from app.models import PresentationStatus
from app.schemas import GeneratedDeck, GenerationRequest, SlideContent


def make_deck() -> GeneratedDeck:
    return GeneratedDeck(
        title="版本管理測試",
        language="zh-TW",
        slides=[
            SlideContent(eyebrow="COVER", title="封面", body="開場", kind="cover"),
            SlideContent(
                eyebrow="01 / 重點",
                title="內容",
                body="需要保留的內容",
                kind="cards",
                image_data="data:image/png;base64,dGVzdA==",
            ),
            SlideContent(eyebrow="END", title="結尾", body="結論", kind="closing"),
        ],
    )


def test_duplicate_deck_creates_new_slide_ids_and_keeps_content() -> None:
    source = make_deck()
    duplicated = _duplicate_deck(source.title, source.model_dump(mode="json"))

    assert duplicated.title == "版本管理測試（副本）"
    assert [slide.id for slide in duplicated.slides] != [slide.id for slide in source.slides]
    assert set(slide.id for slide in duplicated.slides).isdisjoint(
        slide.id for slide in source.slides
    )
    assert duplicated.slides[1].body == source.slides[1].body
    assert duplicated.slides[1].image_data == source.slides[1].image_data


def test_generation_settings_round_trip_provider_ids() -> None:
    provider_id = uuid.uuid4()
    image_provider_id = uuid.uuid4()
    request = GenerationRequest(
        topic="失敗後重試",
        slide_count=6,
        provider_id=provider_id,
        generate_images=True,
        image_provider_id=image_provider_id,
    )

    restored = GenerationRequest.model_validate(request.model_dump(mode="json"))

    assert restored.provider_id == provider_id
    assert restored.image_provider_id == image_provider_id
    assert restored.slide_count == 6


def test_presentation_summary_exposes_retry_state() -> None:
    now = datetime.now(UTC)
    presentation = SimpleNamespace(
        id=uuid.uuid4(),
        title="失敗的簡報",
        language="zh-TW",
        template="editorial",
        status=PresentationStatus.FAILED,
        confirmed_at=None,
        created_at=now,
        updated_at=now,
        slide_count=3,
        content=make_deck().model_dump(mode="json"),
        generation_settings=None,
        revision=2,
        last_rendered_revision=1,
        failed_stage="render",
        last_error="渲染失敗",
    )

    summary = _presentation_read(presentation)

    assert summary.can_retry is True
    assert summary.has_unrendered_changes is True
    assert summary.failed_stage == "render"


def test_download_requires_confirmed_current_output() -> None:
    presentation = SimpleNamespace(
        status=PresentationStatus.PREVIEW_READY,
        confirmed_at=None,
        revision=3,
        last_rendered_revision=3,
    )

    with pytest.raises(HTTPException, match="請先確認簡報內容再下載") as error:
        _ensure_presentation_downloadable(presentation)
    assert error.value.status_code == 409

    presentation.status = PresentationStatus.COMPLETED
    presentation.confirmed_at = datetime.now(UTC)
    _ensure_presentation_downloadable(presentation)

    presentation.revision = 4
    with pytest.raises(HTTPException, match="簡報內容已修改"):
        _ensure_presentation_downloadable(presentation)
