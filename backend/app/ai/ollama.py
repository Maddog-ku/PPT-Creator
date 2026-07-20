import logging
from typing import Any

import httpx

from ..schemas import GeneratedDeck, GenerationRequest, OllamaModelRead, PresentationOutline
from .base import (
    AIProviderError,
    exact_array_schema,
    generation_messages,
    outline_messages,
    parse_generated_deck,
    parse_generated_outline,
)


logger = logging.getLogger(__name__)


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
        base_messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        source_chars = len(request.source_text or "")
        base_context_window = min(
            32_768,
            max(
                8_192,
                request.slide_count * 640,
                source_chars // 3 + request.slide_count * 256 + 2_048,
            ),
        )
        base_output_tokens = min(16_384, max(4_096, request.slide_count * 256))
        response_schema = exact_array_schema(
            GeneratedDeck.model_json_schema(), "slides", request.slide_count
        )
        validation_error: AIProviderError | None = None
        for attempt in range(2):
            messages = list(base_messages)
            if validation_error is not None:
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "上一次輸出無法通過驗證，請重新輸出完整 JSON。"
                            f"必須恰好為 {request.slide_count} 頁，原因："
                            f"{validation_error}"
                        ),
                    }
                )
            payload = {
                "model": self.model,
                "messages": messages,
                "stream": False,
                "format": response_schema,
                # GPT-OSS cannot disable thinking, but "low" prevents reasoning
                # from consuming most of the context before the JSON answer.
                "think": "low",
                "options": {
                    "temperature": 0,
                    "num_ctx": min(32_768, base_context_window * (attempt + 1)),
                    "num_predict": min(
                        16_384, base_output_tokens * (attempt + 1)
                    ),
                },
                # Every attempt unloads the model immediately after its response.
                "keep_alive": 0,
            }
            data = await self._request("POST", "/api/chat", json_body=payload)
            message = data.get("message") or {}
            content = message.get("content") or ""
            try:
                return parse_generated_deck(content, request)
            except AIProviderError as exc:
                validation_error = exc
                logger.warning(
                    "Ollama deck output failed validation%s "
                    "(done_reason=%s, eval_count=%s, content_chars=%s, "
                    "thinking_chars=%s): %s",
                    "; retrying once" if attempt == 0 else "",
                    data.get("done_reason"),
                    data.get("eval_count"),
                    len(content),
                    len(message.get("thinking") or ""),
                    exc,
                )

        assert validation_error is not None
        raise OllamaProviderError(str(validation_error)) from validation_error

    async def generate_outline(
        self, request: GenerationRequest
    ) -> PresentationOutline:
        system, user = outline_messages(request)
        source_chars = len(request.source_text or "")
        base_context_window = min(
            32_768,
            max(
                8_192,
                request.slide_count * 640,
                source_chars // 3 + request.slide_count * 256 + 2_048,
            ),
        )
        base_output_tokens = min(
            16_384, max(4_096, request.slide_count * 256)
        )
        response_schema = exact_array_schema(
            PresentationOutline.model_json_schema(), "items", request.slide_count
        )
        validation_error: AIProviderError | None = None
        for attempt in range(2):
            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ]
            if validation_error is not None:
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "上一次大綱無法通過驗證，請重新輸出完整 JSON。"
                            f"必須恰好為 {request.slide_count} 項，原因："
                            f"{validation_error}"
                        ),
                    }
                )
            data = await self._request(
                "POST",
                "/api/chat",
                json_body={
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                    "format": response_schema,
                    "think": "low",
                    "options": {
                        "temperature": 0,
                        "num_ctx": min(
                            32_768, base_context_window * (attempt + 1)
                        ),
                        "num_predict": min(
                            16_384, base_output_tokens * (attempt + 1)
                        ),
                    },
                    "keep_alive": 0,
                },
            )
            message = data.get("message") or {}
            content = message.get("content") or ""
            try:
                return parse_generated_outline(content, request)
            except AIProviderError as exc:
                validation_error = exc
                logger.warning(
                    "Ollama outline output failed validation%s "
                    "(done_reason=%s, eval_count=%s, content_chars=%s, "
                    "thinking_chars=%s): %s",
                    "; retrying once" if attempt == 0 else "",
                    data.get("done_reason"),
                    data.get("eval_count"),
                    len(content),
                    len(message.get("thinking") or ""),
                    exc,
                )
        assert validation_error is not None
        raise OllamaProviderError(str(validation_error)) from validation_error

    async def release_model(self) -> None:
        await self._request(
            "POST",
            "/api/generate",
            json_body={"model": self.model, "prompt": "", "stream": False, "keep_alive": 0},
        )

    async def generate_image(self, prompt: str, *, image_model: str) -> str:
        payload = {
            "model": image_model,
            "prompt": prompt,
            "width": 1024,
            "height": 576,
            "stream": False,
            "keep_alive": 0,
        }
        data = await self._request("POST", "/api/generate", json_body=payload)
        encoded = data.get("image")
        if not encoded:
            raise OllamaProviderError("Ollama 圖片模型沒有回傳圖片")
        return f"data:image/png;base64,{encoded}"

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
