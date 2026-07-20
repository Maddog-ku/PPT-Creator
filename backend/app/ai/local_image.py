from typing import Any

import httpx

from .base import AIProviderError


class LocalImageProvider:
    """AUTOMATIC1111 Stable Diffusion WebUI API client."""

    provider_type = "stable_diffusion"

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

    async def test_connection(self) -> tuple[bool, list[str], str | None]:
        try:
            data = await self._request("GET", "/sdapi/v1/options")
        except AIProviderError as exc:
            return False, [], str(exc)
        checkpoint = str(data.get("sd_model_checkpoint") or self.model)
        return True, [checkpoint], None

    async def generate_image(self, prompt: str) -> str:
        data = await self._request(
            "POST",
            "/sdapi/v1/txt2img",
            json_body={
                "prompt": prompt,
                "negative_prompt": (
                    "text, words, letters, numbers, typography, caption, label, sign, "
                    "logo, watermark, user interface, screen, packaging, blurry, low quality"
                ),
                "width": 1024,
                "height": 576,
                "steps": 24,
                "cfg_scale": 7,
                "override_settings": {"sd_model_checkpoint": self.model},
                "override_settings_restore_afterwards": True,
            },
        )
        encoded = (data.get("images") or [None])[0]
        if not encoded:
            raise AIProviderError("本機圖片模型沒有回傳圖片")
        if str(encoded).startswith("data:"):
            return str(encoded)
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
            raise AIProviderError(
                f"無法連線本機 Stable Diffusion API：{self.base_url}"
            ) from exc
        except httpx.TimeoutException as exc:
            raise AIProviderError("本機圖片生成逾時，請稍後重試") from exc
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:500]
            raise AIProviderError(
                f"本機圖片 API 回傳 {exc.response.status_code}：{detail}"
            ) from exc
        except ValueError as exc:
            raise AIProviderError("本機圖片 API 回傳無法解析的資料") from exc
        finally:
            if owns_client:
                await client.aclose()
