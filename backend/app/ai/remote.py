import json
import base64
from typing import Any, Literal
from urllib.parse import quote

import httpx

from ..schemas import GeneratedDeck, GenerationRequest, PresentationOutline
from .base import (
    AIProviderError,
    exact_array_schema,
    generation_messages,
    outline_messages,
    parse_generated_deck,
    parse_generated_outline,
)


RemoteProviderType = Literal["openai", "anthropic", "gemini", "openai_compatible"]

OPENAI_SLIDE_ITEM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "label": {"type": "string"},
        "title": {"type": "string"},
        "body": {"type": "string"},
    },
    "required": ["label", "title", "body"],
}

OPENAI_METRIC_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "value": {"type": "string"},
        "label": {"type": "string"},
        "context": {"type": "string"},
    },
    "required": ["value", "label", "context"],
}

OPENAI_COMPARISON_SIDE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "label": {"type": "string"},
        "title": {"type": "string"},
        "body": {"type": "string"},
    },
    "required": ["label", "title", "body"],
}

OPENAI_COMPARISON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "left": OPENAI_COMPARISON_SIDE_SCHEMA,
        "right": OPENAI_COMPARISON_SIDE_SCHEMA,
        "callout": {"type": "string"},
    },
    "required": ["left", "right", "callout"],
}


OPENAI_DECK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "title": {"type": "string"},
        "language": {"type": "string"},
        "slides": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "eyebrow": {"type": "string"},
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                    "kind": {
                        "type": "string",
                        "enum": [
                            "cover",
                            "section",
                            "cards",
                            "split",
                            "metric",
                            "comparison",
                            "roadmap",
                            "quote",
                            "closing",
                        ],
                    },
                    "items": {
                        "type": "array",
                        "items": OPENAI_SLIDE_ITEM_SCHEMA,
                    },
                    "metric": {
                        "anyOf": [
                            OPENAI_METRIC_SCHEMA,
                            {"type": "null"},
                        ]
                    },
                    "comparison": {
                        "anyOf": [
                            OPENAI_COMPARISON_SCHEMA,
                            {"type": "null"},
                        ]
                    },
                    "visual_prompt": {"type": ["string", "null"]},
                },
                "required": [
                    "eyebrow",
                    "title",
                    "body",
                    "kind",
                    "items",
                    "metric",
                    "comparison",
                    "visual_prompt",
                ],
            },
        },
    },
    "required": ["title", "language", "slides"],
}


OPENAI_OUTLINE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "title": {"type": "string"},
        "language": {"type": "string"},
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "eyebrow": {"type": "string"},
                    "title": {"type": "string"},
                    "objective": {"type": "string"},
                    "kind": {
                        "type": "string",
                        "enum": [
                            "cover",
                            "section",
                            "cards",
                            "split",
                            "metric",
                            "comparison",
                            "roadmap",
                            "quote",
                            "closing",
                        ],
                    },
                },
                "required": ["eyebrow", "title", "objective", "kind"],
            },
        },
    },
    "required": ["title", "language", "items"],
}


class RemoteAIProvider:
    def __init__(
        self,
        *,
        provider_type: RemoteProviderType,
        base_url: str,
        model: str,
        api_key: str | None,
        timeout_seconds: float = 300.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.provider_type = provider_type
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key or ""
        self.timeout_seconds = timeout_seconds
        self._client = client

    async def list_model_names(self) -> list[str]:
        if self.provider_type == "gemini":
            data = await self._request("GET", self._gemini_url("/models"))
            return [
                str(item.get("name", "")).removeprefix("models/")
                for item in data.get("models", [])
                if item.get("name")
            ]
        data = await self._request("GET", f"{self.base_url}/models")
        return [str(item.get("id")) for item in data.get("data", []) if item.get("id")]

    async def test_connection(self) -> tuple[bool, list[str], str | None]:
        try:
            models = await self.list_model_names()
        except AIProviderError as exc:
            return False, [], str(exc)
        if self.model not in models:
            return False, models, f"找不到設定的模型：{self.model}"
        return True, models, None

    async def generate_deck(self, request: GenerationRequest) -> GeneratedDeck:
        system, user = generation_messages(request)
        schema = exact_array_schema(
            GeneratedDeck.model_json_schema(), "slides", request.slide_count
        )
        openai_schema = exact_array_schema(
            OPENAI_DECK_SCHEMA, "slides", request.slide_count
        )
        if self.provider_type in {"openai", "openai_compatible"}:
            payload: dict[str, Any] = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.35,
            }
            if self.provider_type == "openai":
                payload["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "presentation",
                        "strict": True,
                        "schema": openai_schema,
                    },
                }
            else:
                payload["response_format"] = {"type": "json_object"}
            data = await self._request("POST", f"{self.base_url}/chat/completions", payload)
            content = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "")
        elif self.provider_type == "anthropic":
            payload = {
                "model": self.model,
                "system": f"{system}\nJSON Schema：{json.dumps(schema, ensure_ascii=False)}",
                "messages": [{"role": "user", "content": user}],
                "max_tokens": 8192,
                "temperature": 0.35,
            }
            data = await self._request("POST", f"{self.base_url}/messages", payload)
            content = "".join(
                str(item.get("text", ""))
                for item in data.get("content", [])
                if item.get("type") == "text"
            )
        else:
            payload = {
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {
                    "temperature": 0.35,
                    "responseMimeType": "application/json",
                },
            }
            model = quote(self.model.removeprefix("models/"), safe="-._")
            data = await self._request(
                "POST",
                self._gemini_url(f"/models/{model}:generateContent"),
                payload,
            )
            content = "".join(
                str(part.get("text", ""))
                for part in (((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
            )
        return parse_generated_deck(content, request)

    async def generate_outline(
        self, request: GenerationRequest
    ) -> PresentationOutline:
        system, user = outline_messages(request)
        schema = exact_array_schema(
            PresentationOutline.model_json_schema(), "items", request.slide_count
        )
        openai_schema = exact_array_schema(
            OPENAI_OUTLINE_SCHEMA, "items", request.slide_count
        )
        if self.provider_type in {"openai", "openai_compatible"}:
            payload: dict[str, Any] = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.2,
            }
            if self.provider_type == "openai":
                payload["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "presentation_outline",
                        "strict": True,
                        "schema": openai_schema,
                    },
                }
            else:
                payload["response_format"] = {"type": "json_object"}
            data = await self._request(
                "POST", f"{self.base_url}/chat/completions", payload
            )
            content = (
                ((data.get("choices") or [{}])[0].get("message") or {}).get(
                    "content"
                )
                or ""
            )
        elif self.provider_type == "anthropic":
            data = await self._request(
                "POST",
                f"{self.base_url}/messages",
                {
                    "model": self.model,
                    "system": f"{system}\nJSON Schema：{json.dumps(schema, ensure_ascii=False)}",
                    "messages": [{"role": "user", "content": user}],
                    "max_tokens": min(
                        16_384, max(4_096, request.slide_count * 256)
                    ),
                    "temperature": 0.2,
                },
            )
            content = "".join(
                str(item.get("text", ""))
                for item in data.get("content", [])
                if item.get("type") == "text"
            )
        else:
            model = quote(self.model.removeprefix("models/"), safe="-._")
            data = await self._request(
                "POST",
                self._gemini_url(f"/models/{model}:generateContent"),
                {
                    "systemInstruction": {"parts": [{"text": system}]},
                    "contents": [{"role": "user", "parts": [{"text": user}]}],
                    "generationConfig": {
                        "temperature": 0.2,
                        "responseMimeType": "application/json",
                    },
                },
            )
            content = "".join(
                str(part.get("text", ""))
                for part in (
                    ((data.get("candidates") or [{}])[0].get("content") or {}).get(
                        "parts"
                    )
                    or []
                )
            )
        return parse_generated_outline(content, request)

    async def generate_image(self, prompt: str, *, image_model: str) -> str:
        if self.provider_type not in {"openai", "openai_compatible"}:
            raise AIProviderError("此 Provider 尚不支援圖片生成")
        data = await self._request(
            "POST",
            f"{self.base_url}/images/generations",
            {
                "model": image_model,
                "prompt": prompt,
                "n": 1,
                "size": "1024x1024",
            },
        )
        result = (data.get("data") or [{}])[0]
        encoded = result.get("b64_json")
        if encoded:
            return f"data:image/png;base64,{encoded}"
        image_url = result.get("url")
        if image_url:
            return await self._download_image(str(image_url))
        raise AIProviderError("圖片 API 沒有回傳圖片資料")

    async def generate_image_with_tool(self, prompt: str) -> str:
        if self.provider_type != "openai":
            raise AIProviderError("只有 OpenAI Responses API 支援圖片生成工具")
        data = await self._request(
            "POST",
            f"{self.base_url}/responses",
            {
                "model": self.model,
                "input": prompt,
                "tools": [{"type": "image_generation", "size": "1536x1024"}],
            },
        )
        for item in data.get("output", []):
            if item.get("type") == "image_generation_call" and item.get("result"):
                return f"data:image/png;base64,{item['result']}"
        raise AIProviderError("OpenAI 模型沒有回傳圖片生成結果")

    async def _download_image(self, url: str) -> str:
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=httpx.Timeout(self.timeout_seconds))
        try:
            response = await client.get(url)
            response.raise_for_status()
            mime = response.headers.get("content-type", "image/png").split(";")[0]
            return f"data:{mime};base64,{base64.b64encode(response.content).decode()}"
        except (httpx.HTTPError, ValueError) as exc:
            raise AIProviderError("無法下載圖片 API 的生成結果") from exc
        finally:
            if owns_client:
                await client.aclose()

    def _gemini_url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _headers(self) -> dict[str, str]:
        if self.provider_type == "anthropic":
            return {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
        if self.provider_type in {"openai", "openai_compatible"}:
            return {"Authorization": f"Bearer {self.api_key}"}
        return {"x-goog-api-key": self.api_key}

    async def _request(
        self,
        method: str,
        url: str,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=httpx.Timeout(self.timeout_seconds))
        try:
            response = await client.request(method, url, json=json_body, headers=self._headers())
            response.raise_for_status()
            return response.json()
        except httpx.ConnectError as exc:
            raise AIProviderError("無法連線指定的 AI API，請確認 Base URL") from exc
        except httpx.TimeoutException as exc:
            raise AIProviderError("AI API 回應逾時，請稍後重試") from exc
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:500]
            raise AIProviderError(f"AI API 回傳 {exc.response.status_code}：{detail}") from exc
        except (json.JSONDecodeError, ValueError) as exc:
            raise AIProviderError("AI API 回傳無法解析的資料") from exc
        finally:
            if owns_client:
                await client.aclose()
