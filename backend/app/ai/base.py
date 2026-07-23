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
    boundary_instruction = (
        "第一頁 kind 必須是 cover，最後一頁必須是 closing。"
        if request.enforce_deck_boundaries
        else "這是完整簡報的一個內容批次；每頁 kind 必須遵守需求中指定的大綱，不要自行加入封面或結尾。"
    )
    system = "\n".join(
        [
            "你是嚴謹的專業簡報內容編輯。只輸出符合指定 JSON Schema 的 JSON，不要輸出解釋、前言或程式碼圍欄。",
            "",
            "【事實與證據規則】",
            "1. 可使用的事實來源依優先順序為：參考內容、使用者明確提供的簡報需求、穩定且無爭議的一般概念。",
            "2. 人名、組織、產品、日期、金額、比例、統計、排名、研究結果、法規、案例、客戶、引言與資料來源，只有在需求或參考內容明確出現時才能使用。",
            "3. 不得虛構、補齊、猜測或外推任何數字、年份、百分比、成效、因果關係、引用、來源與具體案例；不得使用「研究顯示」「數據證明」「業界普遍認為」等無法由輸入驗證的說法。",
            "4. 保留原始資料的主體、單位、期間、比較基準與限定條件，不得把相關性改寫成因果，也不得把建議改寫成既成事實。",
            "5. 資料不足或互相衝突時，不要自行填空或選邊；以「待確認」「資料不足」表達，或改寫成不含未知細節的建議。",
            "6. 推論與建議必須明確使用「建議」「可考慮」「可能」等措辭，不得偽裝成已驗證結論。",
            "7. metric 的每個數值與單位都必須逐字可在需求或參考內容找到；找不到可驗證數字時，改用 cards、split、roadmap、comparison 或 quote。",
            "",
            "【投影簡報寫作規則】",
            "1. 以會議室投影和遠距觀看為前提：每頁只傳達一個結論，保留口頭報告空間，不把講稿塞進投影片。",
            "2. 標題直接寫出結論；中文建議不超過 22 個字，英文建議不超過 12 個單字。",
            "3. 一般 body 最多 2 個短句；中文建議不超過 70 個字，英文建議不超過 30 個單字。",
            "4. cards、roadmap 與 comparison 的每個說明只保留一個重點；中文建議不超過 42 個字，英文建議不超過 18 個單字。",
            "5. 避免長段落、重複敘述、括號堆疊、過多專有名詞與不必要修飾。所有文字必須能以大字體清楚呈現。",
            "",
            "【內容與版型規則】",
            "所有欄位只能使用純文字，不得包含 HTML、Markdown、項目符號標記或換行排版技巧。",
            boundary_instruction,
            "中間頁依內容使用 section、cards、split、metric、comparison、roadmap 或 quote。",
            "section 用於章節轉場；split 用於概念與說明的左右配置；comparison 用於真正需要對照的兩側內容；quote 用於核心主張，不得捏造名人或機構引言。",
            "平衡使用不同頁型，相同 kind 不得連續超過兩頁；版型必須服務內容，不得只為視覺變化而選用。",
            "cards 與 roadmap 必須在 items 提供恰好 3 個互不重複的項目，每項包含 label、title、body。",
            "metric 必須提供 metric.value、metric.label、metric.context；其餘頁型 metric 設為 null。",
            "comparison 必須提供 comparison.left、comparison.right 與 callout；左右兩側各包含 label、title、body，其餘頁型 comparison 設為 null。",
            "不使用 items 的頁型將 items 設為空陣列。body 只保留該頁的一句摘要，不得拿它取代結構化欄位。",
            "每個中間頁可提供 visual_prompt，描述一張與該頁概念一致、無任何文字的橫式專業圖片；圖片描述不得暗示輸入中不存在的事件、人物、品牌、成果或數據。",
            "若該頁不需要圖片，visual_prompt 設為 null。image_data 一律設為 null。",
            "輸出前自行檢查：所有事實可追溯、所有數字有依據、頁數正確、欄位完整、沒有重複重點、沒有超量文字。",
        ]
    )
    user = (
        f"簡報需求：{request.topic}\n"
        f"語言：{request.language}\n"
        f"頁數：{request.slide_count}\n"
        f"風格：{request.template}\n"
        f"參考內容：\n{reference}\n"
        "任務：建立有清楚開場、主體與結論、適合投影報告的完整簡報。\n"
        f"硬性要求：slides 陣列必須恰好包含 {request.slide_count} 頁，不可多也不可少；"
        "若輸入不足以支持某項具體說法，請刪除該說法或明確標示待確認，不得自行補充。"
    )
    return system, user


def outline_messages(request: GenerationRequest) -> tuple[str, str]:
    reference = request.source_text.strip() if request.source_text else "沒有額外參考資料"
    system = "\n".join(
        [
            "你是嚴謹的專業簡報架構編輯。只輸出符合指定 JSON Schema 的 JSON，不要輸出解釋、前言或程式碼圍欄。",
            "此階段只規劃逐頁目的，不撰寫完整投影片，也不得加入需求與參考內容以外的具體事實。",
            "",
            "【防止幻覺】",
            "1. 人名、組織、產品、日期、金額、比例、統計、排名、研究、法規、案例、客戶與引言，只有在需求或參考內容明確出現時才能使用。",
            "2. 不得捏造數字、來源、成效、因果關係或案例；不得以常識猜測缺少的資訊。",
            "3. 資料不足或衝突時，以「待確認」「資料不足」規劃該頁，或改成不依賴未知事實的分析／建議頁。",
            "4. metric 只用於需求或參考內容已有明確數值、單位、主體與期間的內容；否則不得選 metric。",
            "5. quote 只呈現核心主張；除非輸入提供逐字引言與出處，否則不得冒用人物或機構名義。",
            "",
            "【投影與敘事】",
            "1. 每頁只規劃一個觀眾應記住的結論，標題中文建議不超過 22 個字、英文不超過 12 個單字。",
            "2. objective 只用一句簡短文字說明該頁要讓觀眾理解什麼，不得寫成講稿或長段落。",
            "3. 安排清楚的問題、洞察、方案、證據與行動順序；避免不同頁重複同一目的。",
            "4. 第一頁 kind 必須是 cover，最後一頁必須是 closing。",
            "5. 中間頁依內容使用 section、cards、split、metric、comparison、roadmap 或 quote。",
            "6. 每個主要章節開始可用 section；真正需要對照時用 comparison；流程或階段用 roadmap。",
            "7. 平衡使用不同頁型，相同 kind 不得連續超過兩頁；版型必須依內容選擇，不得為變化而濫用。",
            "8. 每 5 至 8 頁可安排一個 section 建立報告節奏，但短簡報不必強行加入。",
            "所有欄位只能使用純文字，不得包含 HTML、Markdown、項目符號標記或虛構引用。",
            "輸出前自行檢查：所有具體說法有輸入依據、沒有不受支持的數字、頁面目的不重複、頁數與首尾頁型正確。",
        ]
    )
    user = (
        f"簡報需求：{request.topic}\n"
        f"語言：{request.language}\n"
        f"頁數：{request.slide_count}\n"
        f"風格：{request.template}\n"
        f"參考內容：\n{reference}\n"
        "任務：規劃有清楚開場、主體與結論，且適合大字投影的逐頁大綱。\n"
        f"硬性要求：items 陣列必須恰好包含 {request.slide_count} 項，不可多也不可少；"
        "若輸入不足以支持某項具體內容，必須刪除、改成建議，或明確標示待確認。"
    )
    return system, user


_NUMERIC_CLAIM_PATTERN = re.compile(
    r"\d+(?:[.,]\d+)*(?:\s*(?:%|％|倍|x|×|年|月|日|元|萬|亿|億|k|m|b))?",
    re.IGNORECASE,
)


def _numeric_claims(text: str) -> set[str]:
    without_structural_ordinals = re.sub(
        r"第\s*\d+\s*(?:頁|步|階段|章|節|部分|項)",
        "",
        text,
    )
    return {
        re.sub(r"[\s,]", "", match.group(0)).lower().replace("％", "%")
        for match in _NUMERIC_CLAIM_PATTERN.finditer(without_structural_ordinals)
    }


def _evidence_text(request: GenerationRequest) -> str:
    original_topic = request.topic.split(
        "\n\n以下是使用者已確認的大綱", maxsplit=1
    )[0]
    return f"{original_topic}\n{request.source_text or ''}"


def _reject_unsupported_numeric_claims(
    texts: list[str], request: GenerationRequest
) -> None:
    evidence_claims = _numeric_claims(_evidence_text(request))
    generated_claims = {
        claim for text in texts for claim in _numeric_claims(text)
    }
    unsupported = sorted(generated_claims - evidence_claims)
    if unsupported:
        raise AIProviderError(
            "模型產生未由需求或參考資料支持的數字："
            f"{', '.join(unsupported)}。請移除、改成待確認，或只使用輸入中已有的數字"
        )


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
    numeric_claim_texts = [deck.title]
    for slide in deck.slides:
        numeric_claim_texts.extend(
            [slide.title, slide.body, slide.visual_prompt or ""]
        )
        numeric_claim_texts.extend(
            text
            for item in slide.items
            for text in (item.title, item.body)
        )
        if slide.metric is not None:
            numeric_claim_texts.extend(
                [
                    slide.metric.value,
                    slide.metric.label,
                    slide.metric.context,
                ]
            )
        if slide.comparison is not None:
            numeric_claim_texts.extend(
                [
                    slide.comparison.left.title,
                    slide.comparison.left.body,
                    slide.comparison.right.title,
                    slide.comparison.right.body,
                    slide.comparison.callout,
                ]
            )
    _reject_unsupported_numeric_claims(numeric_claim_texts, request)
    if (
        request.enforce_deck_boundaries
        and (deck.slides[0].kind != "cover" or deck.slides[-1].kind != "closing")
    ):
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
    _reject_unsupported_numeric_claims(
        [
            outline.title,
            *[
                text
                for item in outline.items
                for text in (item.title, item.objective)
            ],
        ],
        request,
    )
    optimized = optimize_outline_layouts(outline)
    if optimized.items[0].kind != "cover" or optimized.items[-1].kind != "closing":
        raise AIProviderError("模型回傳的大綱缺少封面或結尾")
    return optimized
