import json
import unittest

import httpx

from app.ai import RemoteAIProvider
from app.schemas import GenerationRequest
from app.security import decrypt_api_key, encrypt_api_key


DECK = {
    "title": "跨模型測試",
    "language": "zh-TW",
    "slides": [
        {"eyebrow": "COVER", "title": "跨模型測試", "body": "開場", "kind": "cover"},
        {"eyebrow": "01", "title": "內容", "body": "重點", "kind": "cards"},
        {"eyebrow": "END", "title": "結論", "body": "下一步", "kind": "closing"},
    ],
}


class RemoteProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_openai_uses_chat_completions_api(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/v1/chat/completions")
            self.assertEqual(request.headers["authorization"], "Bearer secret")
            payload = json.loads(request.content)
            self.assertEqual(payload["model"], "test-model")
            self.assertEqual(payload["response_format"]["type"], "json_schema")
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": json.dumps(DECK)}}]},
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = RemoteAIProvider(
                provider_type="openai",
                base_url="https://api.example/v1",
                model="test-model",
                api_key="secret",
                client=client,
            )
            deck = await provider.generate_deck(
                GenerationRequest(topic="測試", slide_count=3)
            )
        self.assertEqual(deck.title, "跨模型測試")

    async def test_anthropic_uses_messages_api(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/v1/messages")
            self.assertEqual(request.headers["x-api-key"], "secret")
            self.assertEqual(request.headers["anthropic-version"], "2023-06-01")
            return httpx.Response(
                200,
                json={"content": [{"type": "text", "text": json.dumps(DECK)}]},
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = RemoteAIProvider(
                provider_type="anthropic",
                base_url="https://api.example/v1",
                model="test-model",
                api_key="secret",
                client=client,
            )
            deck = await provider.generate_deck(
                GenerationRequest(topic="測試", slide_count=3)
            )
        self.assertEqual(len(deck.slides), 3)

    async def test_gemini_uses_generate_content_api(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(
                request.url.path,
                "/v1beta/models/test-model:generateContent",
            )
            self.assertEqual(request.headers["x-goog-api-key"], "secret")
            return httpx.Response(
                200,
                json={
                    "candidates": [
                        {"content": {"parts": [{"text": json.dumps(DECK)}]}}
                    ]
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = RemoteAIProvider(
                provider_type="gemini",
                base_url="https://api.example/v1beta",
                model="test-model",
                api_key="secret",
                client=client,
            )
            deck = await provider.generate_deck(
                GenerationRequest(topic="測試", slide_count=3)
            )
        self.assertEqual(deck.slides[-1].kind, "closing")

    def test_api_key_is_encrypted_at_rest(self) -> None:
        encrypted = encrypt_api_key("top-secret")
        self.assertIsNotNone(encrypted)
        self.assertNotIn("top-secret", encrypted or "")
        self.assertEqual(decrypt_api_key(encrypted), "top-secret")


if __name__ == "__main__":
    unittest.main()
