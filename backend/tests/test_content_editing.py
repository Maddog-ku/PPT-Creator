import uuid

import pytest
from pydantic import ValidationError

from app.schemas import (
    PresentationContentUpdate,
    SlideComparison,
    SlideComparisonSide,
    SlideContent,
    SlideItem,
    SlideMetric,
)


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


def test_legacy_body_only_slide_is_upgraded_to_structured_content() -> None:
    cards = SlideContent(
        eyebrow="01",
        title="三個重點",
        body="理解受眾。建立價值。採取行動。",
        kind="cards",
    )
    metric = SlideContent(
        eyebrow="02",
        title="轉換率提升 42%",
        body="新版流程讓成果更容易理解。",
        kind="metric",
    )

    assert [item.body for item in cards.items] == [
        "理解受眾",
        "建立價值",
        "採取行動",
    ]
    assert metric.metric is not None
    assert metric.metric.value == "42%"


def test_explicit_structured_content_is_preserved() -> None:
    slide = SlideContent(
        eyebrow="03",
        title="方案比較",
        body="比較現況與目標方向。",
        kind="comparison",
        items=[
            SlideItem(label="A", title="不使用", body="不屬於比較欄位"),
        ],
        metric=SlideMetric(value="8", label="週", context="導入週期"),
        comparison=SlideComparison(
            left=SlideComparisonSide(label="現在", title="手動", body="流程分散"),
            right=SlideComparisonSide(label="未來", title="自動", body="流程集中"),
            callout="先從高頻工作開始",
        ),
    )

    assert slide.comparison is not None
    assert slide.comparison.left.title == "手動"
    assert slide.comparison.right.label == "未來"
    assert slide.comparison.callout == "先從高頻工作開始"
