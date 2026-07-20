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

OUTLINE = {
    "title": "跨模型大綱",
    "language": "zh-TW",
    "items": [
        {"eyebrow": "COVER", "title": "跨模型大綱", "objective": "建立主題", "kind": "cover"},
        {"eyebrow": "01", "title": "內容", "objective": "說明重點", "kind": "cards"},
        {"eyebrow": "END", "title": "結論", "objective": "提出行動", "kind": "closing"},
    ],
}


class RemoteProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_openai_outline_uses_strict_schema(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            schema = payload["response_format"]["json_schema"]["schema"]
            self.assertFalse(schema["additionalProperties"])
            self.assertEqual(schema["properties"]["items"]["minItems"], 3)
            self.assertEqual(schema["properties"]["items"]["maxItems"], 3)
            item_schema = schema["properties"]["items"]["items"]
            self.assertFalse(item_schema["additionalProperties"])
            self.assertEqual(set(item_schema["required"]), set(item_schema["properties"]))
            self.assertNotIn("id", item_schema["properties"])
            return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(OUTLINE)}}]})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = RemoteAIProvider(provider_type="openai", base_url="https://api.example/v1", model="test-model", api_key="secret", client=client)
            outline = await provider.generate_outline(GenerationRequest(topic="測試", slide_count=3))

        self.assertEqual(outline.items[-1].kind, "closing")

    async def test_openai_text_model_uses_image_generation_tool(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/v1/responses")
            payload = json.loads(request.content)
            self.assertEqual(payload["model"], "gpt-text-with-tools")
            self.assertEqual(payload["tools"][0]["type"], "image_generation")
            return httpx.Response(
                200,
                json={"output": [{"type": "image_generation_call", "result": "aW1hZ2U="}]},
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = RemoteAIProvider(
                provider_type="openai",
                base_url="https://api.example/v1",
                model="gpt-text-with-tools",
                api_key="secret",
                client=client,
            )
            image = await provider.generate_image_with_tool("A clean chart")
        self.assertEqual(image, "data:image/png;base64,aW1hZ2U=")

    async def test_openai_generates_image_data_url(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/v1/images/generations")
            payload = json.loads(request.content)
            self.assertEqual(payload["model"], "gpt-image-test")
            return httpx.Response(200, json={"data": [{"b64_json": "aW1hZ2U="}]})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = RemoteAIProvider(
                provider_type="openai",
                base_url="https://api.example/v1",
                model="text-model",
                api_key="secret",
                client=client,
            )
            image = await provider.generate_image("A clean chart", image_model="gpt-image-test")
        self.assertEqual(image, "data:image/png;base64,aW1hZ2U=")

    async def test_openai_uses_chat_completions_api(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/v1/chat/completions")
            self.assertEqual(request.headers["authorization"], "Bearer secret")
            payload = json.loads(request.content)
            self.assertEqual(payload["model"], "test-model")
            self.assertEqual(payload["response_format"]["type"], "json_schema")
            schema = payload["response_format"]["json_schema"]["schema"]
            self.assertFalse(schema["additionalProperties"])
            self.assertEqual(schema["properties"]["slides"]["minItems"], 3)
            self.assertEqual(schema["properties"]["slides"]["maxItems"], 3)
            self.assertEqual(set(schema["required"]), set(schema["properties"]))
            slide_schema = schema["properties"]["slides"]["items"]
            self.assertFalse(slide_schema["additionalProperties"])
            self.assertEqual(
                set(slide_schema["required"]), set(slide_schema["properties"])
            )
            self.assertNotIn("id", slide_schema["properties"])
            self.assertNotIn("image_data", slide_schema["properties"])
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
