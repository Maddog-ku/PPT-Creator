import uuid

import pytest
from pydantic import ValidationError

from app.schemas import PresentationContentUpdate, SlideContent


def make_slide(kind: str = "cards") -> SlideContent:
    return SlideContent(
        eyebrow="01 / TEST",
        title="可編輯投影片",
        body="這是一段可儲存的投影片內容。",
        kind=kind,
    )


def test_slide_ids_are_stable_and_unique() -> None:
    first = make_slide()
    second = make_slide()

    assert isinstance(first.id, uuid.UUID)
    assert first.id != second.id
    assert SlideContent.model_validate(first.model_dump()).id == first.id


def test_content_update_requires_at_least_three_slides() -> None:
    with pytest.raises(ValidationError):
        PresentationContentUpdate(
            title="測試簡報",
            language="zh-TW",
            slides=[make_slide("cover"), make_slide("closing")],
        )


def test_content_update_preserves_slide_ids() -> None:
    slides = [make_slide("cover"), make_slide(), make_slide("closing")]
    payload = PresentationContentUpdate(
        title="測試簡報",
        language="zh-TW",
        slides=slides,
    )

    encoded = payload.model_dump(mode="json")
    assert encoded["slides"][0]["id"] == str(slides[0].id)
