import json
import re
from typing import Protocol

from ..schemas import GeneratedDeck, GenerationRequest


class AIProviderError(RuntimeError):
    """Raised when an AI provider cannot complete a request."""


class AIProvider(Protocol):
    provider_type: str
    model: str

    async def list_model_names(self) -> list[str]: ...

    async def test_connection(self) -> tuple[bool, list[str], str | None]: ...

    async def generate_deck(self, request: GenerationRequest) -> GeneratedDeck: ...


def generation_messages(request: GenerationRequest) -> tuple[str, str]:
    reference = request.source_text.strip() if request.source_text else "沒有額外參考資料"
    system = (
        "你是專業簡報內容編輯。只輸出符合指定 JSON Schema 的內容。"
        "每頁只傳達一個重點，標題簡潔，內文可直接放入簡報。"
        "所有欄位只能使用純文字，不得包含 HTML、Markdown 或項目符號標記。"
        "第一頁 kind 必須是 cover，最後一頁必須是 closing；"
        "中間頁依內容使用 cards、metric 或 roadmap。"
    )
    user = (
        f"簡報需求：{request.topic}\n"
        f"語言：{request.language}\n"
        f"頁數：{request.slide_count}\n"
        f"風格：{request.template}\n"
        f"參考內容：\n{reference}\n"
        "請建立有清楚開場、主體與結論的完整簡報。"
    )
    return system, user


def parse_generated_deck(content: str, request: GenerationRequest) -> GeneratedDeck:
    content = content.strip()
    if not content:
        raise AIProviderError("AI 模型沒有回傳簡報內容")
    if content.startswith("```"):
        content = content.removeprefix("```json").removeprefix("```")
        content = content.removesuffix("```").strip()
    if not content.startswith("{"):
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            content = match.group(0)
    try:
        deck = GeneratedDeck.model_validate(json.loads(content))
    except (json.JSONDecodeError, ValueError) as exc:
        raise AIProviderError(f"模型回傳格式不正確：{exc}") from exc
    if len(deck.slides) != request.slide_count:
        raise AIProviderError(
            f"模型回傳 {len(deck.slides)} 頁，預期為 {request.slide_count} 頁"
        )
    if deck.slides[0].kind != "cover" or deck.slides[-1].kind != "closing":
        raise AIProviderError("模型回傳的封面或結尾頁型不正確")
    return deck
