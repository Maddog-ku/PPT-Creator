from app.schemas import (
    GeneratedDeck,
    GenerationRequest,
    OutlineItem,
    PresentationOutline,
    SlideContent,
)
from app.main import _generation_job_can_retry
from app.models import PresentationStatus
from app.worker import _apply_confirmed_outline, _request_with_confirmed_outline


def test_only_latest_failed_job_is_retryable() -> None:
    assert _generation_job_can_retry("FAILED", PresentationStatus.FAILED, 1) is True
    assert _generation_job_can_retry("FAILED", PresentationStatus.FAILED, 2) is False
    assert _generation_job_can_retry("FAILED", PresentationStatus.PREVIEW_READY, 1) is False
    assert _generation_job_can_retry("COMPLETED", PresentationStatus.FAILED, 1) is False


def test_confirmed_outline_is_added_to_content_request() -> None:
    request = GenerationRequest(topic="原始主題", slide_count=3)
    outline = PresentationOutline(
        title="確認後大綱",
        language="zh-TW",
        items=[
            OutlineItem(eyebrow="COVER", title="封面", objective="建立主題", kind="cover"),
            OutlineItem(eyebrow="01", title="關鍵內容", objective="解釋策略", kind="cards"),
            OutlineItem(eyebrow="END", title="下一步", objective="提出行動", kind="closing"),
        ],
    )

    content_request = _request_with_confirmed_outline(request, outline)

    assert content_request.slide_count == 3
    assert "使用者已確認的大綱" in content_request.topic
    assert "關鍵內容：解釋策略" in content_request.topic


def test_confirmed_outline_fields_override_model_drift() -> None:
    outline = PresentationOutline(
        title="使用者確認的標題",
        language="zh-TW",
        items=[
            OutlineItem(eyebrow="開場", title="確認封面", objective="開場", kind="cover"),
            OutlineItem(eyebrow="策略", title="確認路線圖", objective="說明執行", kind="roadmap"),
            OutlineItem(eyebrow="結語", title="確認結尾", objective="收尾", kind="closing"),
        ],
    )
    model_deck = GeneratedDeck(
        title="模型自行更改的標題",
        language="en",
        slides=[
            SlideContent(eyebrow="A", title="錯誤一", body="模型內容一", kind="cover"),
            SlideContent(eyebrow="B", title="錯誤二", body="模型內容二", kind="metric"),
            SlideContent(eyebrow="C", title="錯誤三", body="模型內容三", kind="closing"),
        ],
    )

    deck = _apply_confirmed_outline(model_deck, outline)

    assert deck.title == outline.title
    assert deck.language == outline.language
    assert [slide.title for slide in deck.slides] == [item.title for item in outline.items]
    assert [slide.eyebrow for slide in deck.slides] == [item.eyebrow for item in outline.items]
    assert [slide.kind for slide in deck.slides] == [item.kind for item in outline.items]
    assert deck.slides[1].body == "模型內容二"
