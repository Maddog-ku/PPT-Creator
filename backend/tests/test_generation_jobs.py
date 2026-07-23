from app.schemas import (
    GeneratedDeck,
    GenerationRequest,
    OutlineItem,
    PresentationOutline,
    SlideContent,
)
from app.main import _generation_job_can_retry
from app.models import PresentationStatus
from app.worker import (
    _apply_confirmed_outline,
    _partition_outline,
    _release_local_resources,
    _request_with_confirmed_outline,
)


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


def test_large_outline_is_partitioned_into_balanced_batches() -> None:
    items = [
        OutlineItem(
            eyebrow=f"{index + 1:02d}",
            title=f"第 {index + 1} 頁",
            objective="說明重點",
            kind=(
                "cover"
                if index == 0
                else "closing"
                if index == 21
                else "cards"
            ),
        )
        for index in range(22)
    ]
    outline = PresentationOutline(
        title="大型簡報",
        language="zh-TW",
        items=items,
    )

    batches = _partition_outline(outline)

    assert [len(batch.items) for _, batch in batches] == [8, 7, 7]
    assert [offset for offset, _ in batches] == [0, 8, 15]
    assert [
        item.title for _, batch in batches for item in batch.items
    ] == [item.title for item in outline.items]


def test_batch_request_preserves_global_page_numbers_without_forcing_boundaries() -> None:
    request = GenerationRequest(topic="原始主題", slide_count=12)
    outline = PresentationOutline(
        title="第二批",
        language="zh-TW",
        items=[
            OutlineItem(eyebrow="07", title="現況", objective="說明現況", kind="cards"),
            OutlineItem(eyebrow="08", title="方案", objective="比較方案", kind="comparison"),
            OutlineItem(eyebrow="09", title="執行", objective="提出步驟", kind="roadmap"),
        ],
    )

    batch_request = _request_with_confirmed_outline(
        request,
        outline,
        page_offset=6,
        enforce_deck_boundaries=False,
    )

    assert batch_request.slide_count == 3
    assert batch_request.enforce_deck_boundaries is False
    assert "7. [cards] 現況" in batch_request.topic
    assert "只生成第 7 至 9 頁" in batch_request.topic


async def test_releases_default_text_and_image_models(monkeypatch) -> None:
    released: list[str] = []

    class FakeOllamaProvider:
        def __init__(self, *, model: str, **_kwargs) -> None:
            self.model = model

        async def release_model(self) -> None:
            released.append(self.model)

    monkeypatch.setattr("app.worker.OllamaProvider", FakeOllamaProvider)

    await _release_local_resources(
        GenerationRequest(
            topic="資源釋放",
            slide_count=10,
            generate_images=True,
            image_count=2,
        )
    )

    assert set(released) == {"gpt-oss:20b", "x/z-image-turbo"}
