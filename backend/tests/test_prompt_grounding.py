import json

import pytest

from app.ai.base import (
    AIProviderError,
    generation_messages,
    outline_messages,
    parse_generated_deck,
    parse_generated_outline,
)
from app.schemas import GenerationRequest


def _deck_with_title(title: str) -> str:
    return json.dumps(
        {
            "title": "營運策略",
            "language": "zh-TW",
            "slides": [
                {
                    "eyebrow": "COVER",
                    "title": "營運策略",
                    "body": "聚焦可驗證的資訊",
                    "kind": "cover",
                },
                {
                    "eyebrow": "FOCUS",
                    "title": title,
                    "body": "先確認資料再提出行動",
                    "kind": "cards",
                },
                {
                    "eyebrow": "NEXT",
                    "title": "下一步",
                    "body": "補齊資料並驗證方案",
                    "kind": "closing",
                },
            ],
        },
        ensure_ascii=False,
    )


def test_generation_prompt_requires_grounding_and_projection_copy() -> None:
    request = GenerationRequest(
        topic="依正式報告整理營運策略",
        source_text="正式報告記錄轉換率提升 42%。",
        slide_count=6,
    )

    system, user = generation_messages(request)

    assert "不得虛構、補齊、猜測或外推任何數字" in system
    assert "相關性改寫成因果" in system
    assert "中文建議不超過 22 個字" in system
    assert "每頁只傳達一個結論" in system
    assert "若輸入不足以支持某項具體說法" in user
    assert "正式報告記錄轉換率提升 42%" in user


def test_outline_prompt_forbids_unverified_metrics_and_quotes() -> None:
    system, _ = outline_messages(
        GenerationRequest(topic="規劃產品簡報", slide_count=3)
    )

    assert "metric 只用於需求或參考內容已有明確數值" in system
    assert "不得冒用人物或機構名義" in system
    assert "資料不足" in system
    assert "標題中文建議不超過 22 個字" in system


def test_rejects_numeric_claim_not_present_in_input() -> None:
    request = GenerationRequest(topic="營運策略", slide_count=3)

    with pytest.raises(AIProviderError, match="未由需求或參考資料支持的數字"):
        parse_generated_deck(_deck_with_title("轉換率提升 42%"), request)


def test_accepts_numeric_claim_present_in_reference() -> None:
    request = GenerationRequest(
        topic="營運策略",
        source_text="正式報表顯示轉換率提升 42%。",
        slide_count=3,
    )

    deck = parse_generated_deck(_deck_with_title("轉換率提升 42%"), request)

    assert deck.slides[1].title == "轉換率提升 42%"


def test_allows_structural_page_and_step_numbers() -> None:
    request = GenerationRequest(topic="營運策略", slide_count=3)

    deck = parse_generated_deck(_deck_with_title("第 3 步：驗證方案"), request)

    assert deck.slides[1].title == "第 3 步：驗證方案"


def test_rejects_unsupported_number_in_outline() -> None:
    content = json.dumps(
        {
            "title": "營運策略",
            "language": "zh-TW",
            "items": [
                {
                    "eyebrow": "COVER",
                    "title": "營運策略",
                    "objective": "建立報告脈絡",
                    "kind": "cover",
                },
                {
                    "eyebrow": "FOCUS",
                    "title": "成本降低 30%",
                    "objective": "說明成本成果",
                    "kind": "metric",
                },
                {
                    "eyebrow": "NEXT",
                    "title": "下一步",
                    "objective": "提出資料驗證行動",
                    "kind": "closing",
                },
            ],
        },
        ensure_ascii=False,
    )

    with pytest.raises(AIProviderError, match="30%"):
        parse_generated_outline(
            content,
            GenerationRequest(topic="營運策略", slide_count=3),
        )
