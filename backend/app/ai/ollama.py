from typing import Any

import httpx

from ..schemas import GeneratedDeck, GenerationRequest, OllamaModelRead
from .base import AIProviderError, generation_messages, parse_generated_deck


class OllamaProviderError(AIProviderError):
    """Raised when the local Ollama service cannot complete a request."""


class OllamaProvider:
    provider_type = "ollama"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: float = 300.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self._client = client

    async def list_models(self) -> list[OllamaModelRead]:
        data = await self._request("GET", "/api/tags")
        models: list[OllamaModelRead] = []
        for item in data.get("models", []):
            details = item.get("details") or {}
            models.append(
                OllamaModelRead(
                    name=item.get("name") or item.get("model") or "unknown",
                    size=item.get("size"),
                    parameter_size=details.get("parameter_size"),
                    quantization_level=details.get("quantization_level"),
                )
            )
        return models

    async def list_model_names(self) -> list[str]:
        return [item.name for item in await self.list_models()]

    async def test_connection(self) -> tuple[bool, list[str], str | None]:
        try:
            names = await self.list_model_names()
        except OllamaProviderError as exc:
            return False, [], str(exc)
        if self.model not in names:
            return False, names, f"找不到設定的模型：{self.model}"
        return True, names, None

    async def generate_deck(self, request: GenerationRequest) -> GeneratedDeck:
        system, user = generation_messages(request)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "format": GeneratedDeck.model_json_schema(),
            "options": {"temperature": 0.35},
            "keep_alive": "10m",
        }
        data = await self._request("POST", "/api/chat", json_body=payload)
        try:
            return parse_generated_deck(
                ((data.get("message") or {}).get("content") or ""), request
            )
        except AIProviderError as exc:
            raise OllamaProviderError(str(exc)) from exc

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(self.timeout_seconds),
        )
        try:
            response = await client.request(method, path, json=json_body)
            response.raise_for_status()
            return response.json()
        except httpx.ConnectError as exc:
            raise OllamaProviderError(
                f"無法連線 Ollama：{self.base_url}。請確認 Ollama 已啟動。"
            ) from exc
        except httpx.TimeoutException as exc:
            raise OllamaProviderError("Ollama 生成逾時，請稍後重試") from exc
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:500]
            raise OllamaProviderError(
                f"Ollama 回傳 {exc.response.status_code}：{detail}"
            ) from exc
        except ValueError as exc:
            raise OllamaProviderError("Ollama 回傳無法解析的資料") from exc
        finally:
            if owns_client:
                await client.aclose()
