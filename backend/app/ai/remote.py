import json
from typing import Any, Literal
from urllib.parse import quote

import httpx

from ..schemas import GeneratedDeck, GenerationRequest
from .base import AIProviderError, generation_messages, parse_generated_deck


RemoteProviderType = Literal["openai", "anthropic", "gemini", "openai_compatible"]


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
        schema = GeneratedDeck.model_json_schema()
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
                    "json_schema": {"name": "presentation", "strict": True, "schema": schema},
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
