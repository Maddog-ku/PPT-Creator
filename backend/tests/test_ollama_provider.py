import json
import unittest

import httpx

from app.ai import OllamaProvider, OllamaProviderError
from app.schemas import GenerationRequest, SlideContent


class OllamaProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_lists_local_models(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/api/tags")
            return httpx.Response(
                200,
                json={
                    "models": [
                        {
                            "name": "gpt-oss:20b",
                            "size": 13_793_441_244,
                            "details": {
                                "parameter_size": "20.9B",
                                "quantization_level": "MXFP4",
                            },
                        }
                    ]
                },
            )

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="http://ollama.test",
        ) as client:
            provider = OllamaProvider(
                base_url="http://ollama.test",
                model="gpt-oss:20b",
                client=client,
            )
            models = await provider.list_models()

        self.assertEqual(models[0].name, "gpt-oss:20b")
        self.assertEqual(models[0].parameter_size, "20.9B")

    async def test_generates_schema_valid_deck(self) -> None:
        deck = {
            "title": "測試簡報",
            "language": "zh-TW",
            "slides": [
                {"eyebrow": "COVER", "title": "測試簡報", "body": "開場", "kind": "cover"},
                {"eyebrow": "01", "title": "核心內容", "body": "重點內容", "kind": "cards"},
                {"eyebrow": "END", "title": "結論", "body": "下一步", "kind": "closing"},
            ],
        }

        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            self.assertEqual(request.url.path, "/api/chat")
            self.assertEqual(payload["model"], "gpt-oss:20b")
            self.assertEqual(payload["stream"], False)
            self.assertIn("format", payload)
            return httpx.Response(200, json={"message": {"content": json.dumps(deck)}})

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="http://ollama.test",
        ) as client:
            provider = OllamaProvider(
                base_url="http://ollama.test",
                model="gpt-oss:20b",
                client=client,
            )
            result = await provider.generate_deck(
                GenerationRequest(topic="測試", slide_count=3)
            )

        self.assertEqual(result.title, "測試簡報")
        self.assertEqual(len(result.slides), 3)

    async def test_rejects_empty_model_response(self) -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"message": {"content": ""}})

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="http://ollama.test",
        ) as client:
            provider = OllamaProvider(
                base_url="http://ollama.test",
                model="gpt-oss:20b",
                client=client,
            )
            with self.assertRaises(OllamaProviderError):
                await provider.generate_deck(
                    GenerationRequest(topic="測試", slide_count=3)
                )

    def test_slide_content_removes_html(self) -> None:
        slide = SlideContent(
            eyebrow="01",
            title="重點",
            body="<ul><li>第一點</li><li>第二點</li></ul>",
            kind="cards",
        )
        self.assertEqual(slide.body, "第一點 第二點")


if __name__ == "__main__":
    unittest.main()
