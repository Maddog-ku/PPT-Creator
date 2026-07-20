from copy import deepcopy
import json
import re
from typing import Any, Protocol

from ..schemas import GeneratedDeck, GenerationRequest, PresentationOutline


class AIProviderError(RuntimeError):
    """Raised when an AI provider cannot complete a request."""


class AIProvider(Protocol):
    provider_type: str
    model: str

    async def list_model_names(self) -> list[str]: ...

    async def test_connection(self) -> tuple[bool, list[str], str | None]: ...

    async def generate_deck(self, request: GenerationRequest) -> GeneratedDeck: ...

    async def generate_outline(
        self, request: GenerationRequest
    ) -> PresentationOutline: ...


def exact_array_schema(
    schema: dict[str, Any], field_name: str, item_count: int
) -> dict[str, Any]:
    """Return a schema that requires an exact number of array items."""
    exact_schema = deepcopy(schema)
    try:
        array_schema = exact_schema["properties"][field_name]
    except (KeyError, TypeError) as exc:
        raise ValueError(f"JSON Schema does not contain array field: {field_name}") from exc
    if array_schema.get("type") != "array":
        raise ValueError(f"JSON Schema field is not an array: {field_name}")
    array_schema["minItems"] = item_count
    array_schema["maxItems"] = item_count
    return exact_schema


def generation_messages(request: GenerationRequest) -> tuple[str, str]:
    reference = request.source_text.strip() if request.source_text else "沒有額外參考資料"
    system = (
        "你是專業簡報內容編輯。只輸出符合指定 JSON Schema 的內容。"
        "每頁只傳達一個重點，標題簡潔，內文可直接放入簡報。"
        "所有欄位只能使用純文字，不得包含 HTML、Markdown 或項目符號標記。"
        "第一頁 kind 必須是 cover，最後一頁必須是 closing。"
        "中間頁依內容使用 section、cards、split、metric、comparison、roadmap 或 quote。"
        "section 用於章節轉場，split 用於左右圖文，comparison 用於比較，quote 用於關鍵主張。"
        "請平衡使用不同頁型，相同 kind 不得連續超過兩頁，讓整份簡報有明顯視覺節奏。"
        "每頁標題要能直接說出結論；內文拆成最多三個短句，方便講者掃讀。"
        "metric 只能使用需求或參考資料中確實存在的數字，不得虛構統計值。"
        "每個中間頁可提供 visual_prompt，描述一張適合該頁、無任何文字的橫式專業圖片；"
        "若該頁不需要圖片則設為 null。image_data 一律設為 null。"
    )
    user = (
        f"簡報需求：{request.topic}\n"
        f"語言：{request.language}\n"
        f"頁數：{request.slide_count}\n"
        f"風格：{request.template}\n"
        f"參考內容：\n{reference}\n"
        "請建立有清楚開場、主體與結論的完整簡報。"
        f"slides 陣列必須恰好包含 {request.slide_count} 頁，不可多也不可少。"
    )
    return system, user


def outline_messages(request: GenerationRequest) -> tuple[str, str]:
    reference = request.source_text.strip() if request.source_text else "沒有額外參考資料"
    system = (
        "你是專業簡報架構編輯。只輸出符合指定 JSON Schema 的內容。"
        "此階段只規劃每一頁的目的，不撰寫完整投影片。"
        "所有欄位只能使用純文字，不得包含 HTML 或 Markdown。"
        "第一頁 kind 必須是 cover，最後一頁必須是 closing。"
        "中間頁依內容使用 section、cards、split、metric、comparison、roadmap 或 quote。"
        "每個主要章節開始可用 section；需要對照時用 comparison；核心主張可用 quote。"
        "請平衡使用不同頁型，相同 kind 不得連續超過兩頁。"
        "版型必須依該頁內容選擇，不要為了變化而使用不適合的版型。"
        "metric 只用於已有可信數字的內容；每 5 至 8 頁可安排一個 section 建立報告節奏。"
        "objective 用一句話說明該頁要讓觀眾理解什麼。"
    )
    user = (
        f"簡報需求：{request.topic}\n"
        f"語言：{request.language}\n"
        f"頁數：{request.slide_count}\n"
        f"風格：{request.template}\n"
        f"參考內容：\n{reference}\n"
        "請規劃有清楚開場、主體與結論的逐頁大綱。"
        f"items 陣列必須恰好包含 {request.slide_count} 項，不可多也不可少。"
    )
    return system, user


def optimize_outline_layouts(outline: PresentationOutline) -> PresentationOutline:
    """Choose stronger content-aware layouts when a model falls back to cards."""
    optimized = []
    for index, item in enumerate(outline.items):
        if index == 0:
            optimized.append(item.model_copy(update={"kind": "cover"}))
            continue
        if index == len(outline.items) - 1:
            optimized.append(item.model_copy(update={"kind": "closing"}))
            continue
        if item.kind in {"cover", "closing"}:
            replacement = "section" if index < len(outline.items) - 2 else "quote"
            optimized.append(item.model_copy(update={"kind": replacement}))
            continue
        if item.kind != "cards":
            optimized.append(item)
            continue

        # Eyebrows commonly contain page numbers, which are not content metrics.
        text = f"{item.title} {item.objective}".lower()
        if re.search(r"\d[\d,.]*\s*(?:%|倍|x|×)?|指標|數據|成長|成本|比例|績效", text):
            kind = "metric"
        elif re.search(r"比較|對照|差異|優缺點|取捨|versus|\bvs\.?\b", text):
            kind = "comparison"
        elif re.search(r"流程|步驟|階段|路徑|時程|里程碑|導入|roadmap", text):
            kind = "roadmap"
        elif re.search(r"章節|單元|篇章|chapter|\bpart\s+\d+", text):
            kind = "section"
        elif re.search(r"核心觀點|核心主張|關鍵啟示|一句話|原則|結論", text):
            kind = "quote"
        elif re.search(r"案例|情境|人物|產品|架構|原理|運作方式", text):
            kind = "split"
        else:
            kind = item.kind

        if (
            len(optimized) >= 2
            and optimized[-1].kind == kind
            and optimized[-2].kind == kind
        ):
            kind = ("split", "quote", "comparison")[index % 3]
        optimized.append(item.model_copy(update={"kind": kind}))

    return outline.model_copy(update={"items": optimized})


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


def parse_generated_outline(
    content: str, request: GenerationRequest
) -> PresentationOutline:
    content = content.strip()
    if not content:
        raise AIProviderError("AI 模型沒有回傳簡報大綱")
    if content.startswith("```"):
        content = content.removeprefix("```json").removeprefix("```")
        content = content.removesuffix("```").strip()
    if not content.startswith("{"):
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            content = match.group(0)
    try:
        outline = PresentationOutline.model_validate(json.loads(content))
    except (json.JSONDecodeError, ValueError) as exc:
        raise AIProviderError(f"模型回傳的大綱格式不正確：{exc}") from exc
    if len(outline.items) != request.slide_count:
        raise AIProviderError(
            f"模型回傳 {len(outline.items)} 項大綱，預期為 {request.slide_count} 項"
        )
    optimized = optimize_outline_layouts(outline)
    if optimized.items[0].kind != "cover" or optimized.items[-1].kind != "closing":
        raise AIProviderError("模型回傳的大綱缺少封面或結尾")
    return optimized
