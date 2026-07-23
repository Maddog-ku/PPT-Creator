import json
import unittest

import httpx

from app.ai import OllamaProvider, OllamaProviderError
from app.ai.base import optimize_outline_layouts
from app.schemas import GenerationRequest, OutlineItem, PresentationOutline, SlideContent


class OllamaProviderTests(unittest.IsolatedAsyncioTestCase):
    def test_optimizes_generic_cards_using_content_signals(self) -> None:
        outline = PresentationOutline(
            title="內容導向版型",
            language="zh-TW",
            items=[
                OutlineItem(eyebrow="C", title="封面", objective="開場", kind="cover"),
                OutlineItem(eyebrow="01", title="成長 42%", objective="說明績效", kind="cards"),
                OutlineItem(eyebrow="02", title="方案比較", objective="對照優缺點", kind="cards"),
                OutlineItem(eyebrow="03", title="導入步驟", objective="三階段流程", kind="cards"),
                OutlineItem(eyebrow="04", title="核心主張", objective="一句話結論", kind="cards"),
                OutlineItem(eyebrow="E", title="結尾", objective="收尾", kind="closing"),
            ],
        )

        result = optimize_outline_layouts(outline)

        self.assertEqual(
            [item.kind for item in result.items],
            ["cover", "metric", "comparison", "roadmap", "quote", "closing"],
        )

    def test_optimizes_cover_closing_positions_without_regeneration(self) -> None:
        outline = PresentationOutline(
            title="位置校正",
            language="zh-TW",
            items=[
                OutlineItem(eyebrow="01", title="開場", objective="建立主題", kind="section"),
                OutlineItem(eyebrow="02", title="內容", objective="說明重點", kind="closing"),
                OutlineItem(eyebrow="03", title="討論", objective="帶出結論", kind="cards"),
            ],
        )

        result = optimize_outline_layouts(outline)

        self.assertEqual([item.kind for item in result.items], ["cover", "quote", "closing"])

    async def test_generates_schema_valid_outline(self) -> None:
        outline = {
            "title": "大綱測試",
            "language": "zh-TW",
            "items": [
                {"eyebrow": "COVER", "title": "大綱測試", "objective": "建立主題", "kind": "cover"},
                {"eyebrow": "01", "title": "核心內容", "objective": "說明重點", "kind": "cards"},
                {"eyebrow": "END", "title": "下一步", "objective": "提出行動", "kind": "closing"},
            ],
        }

        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            self.assertEqual(request.url.path, "/api/chat")
            self.assertEqual(payload["keep_alive"], 0)
            items_schema = payload["format"]["properties"]["items"]
            self.assertEqual(items_schema["minItems"], 3)
            self.assertEqual(items_schema["maxItems"], 3)
            return httpx.Response(200, json={"message": {"content": json.dumps(outline)}})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://ollama.test") as client:
            provider = OllamaProvider(base_url="http://ollama.test", model="gpt-oss:20b", client=client)
            result = await provider.generate_outline(GenerationRequest(topic="測試", slide_count=3))

        self.assertEqual(result.title, "大綱測試")
        self.assertEqual(len(result.items), 3)

    async def test_generates_local_image_and_unloads_model(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/api/generate")
            payload = json.loads(request.content)
            self.assertEqual(payload["model"], "x/z-image-turbo")
            self.assertEqual(payload["keep_alive"], 0)
            self.assertEqual(payload["stream"], False)
            return httpx.Response(200, json={"image": "aW1hZ2U=", "done": True})

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="http://ollama.test",
        ) as client:
            provider = OllamaProvider(
                base_url="http://ollama.test",
                model="gpt-oss:20b",
                client=client,
            )
            image = await provider.generate_image(
                "A clean chart",
                image_model="x/z-image-turbo",
            )
        self.assertEqual(image, "data:image/png;base64,aW1hZ2U=")

    async def test_releases_a_specific_model(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            self.assertEqual(payload["model"], "x/z-image-turbo")
            self.assertEqual(payload["keep_alive"], 0)
            return httpx.Response(200, json={"done": True})

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="http://ollama.test",
        ) as client:
            provider = OllamaProvider(
                base_url="http://ollama.test",
                model="gpt-oss:20b",
                client=client,
            )
            await provider.release_model("x/z-image-turbo")

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
            self.assertEqual(payload["keep_alive"], 0)
            self.assertEqual(payload["think"], "low")
            self.assertEqual(payload["options"]["temperature"], 0)
            self.assertEqual(payload["options"]["num_ctx"], 8192)
            self.assertEqual(payload["options"]["num_predict"], 4096)
            slides_schema = payload["format"]["properties"]["slides"]
            self.assertEqual(slides_schema["minItems"], 3)
            self.assertEqual(slides_schema["maxItems"], 3)
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

    async def test_retries_once_after_invalid_model_response(self) -> None:
        deck = {
            "title": "重試成功",
            "language": "zh-TW",
            "slides": [
                {"eyebrow": "COVER", "title": "開場", "body": "開場", "kind": "cover"},
                {"eyebrow": "01", "title": "重點", "body": "內容", "kind": "cards"},
                {"eyebrow": "END", "title": "結論", "body": "下一步", "kind": "closing"},
            ],
        }
        requests: list[dict[str, object]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            requests.append(payload)
            if len(requests) == 1:
                return httpx.Response(200, json={"message": {"content": ""}})
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

        self.assertEqual(result.title, "重試成功")
        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[0]["keep_alive"], 0)
        self.assertEqual(requests[1]["keep_alive"], 0)
        self.assertEqual(requests[1]["think"], "low")
        self.assertEqual(
            requests[1]["options"],
            {"temperature": 0, "num_ctx": 16384, "num_predict": 8192},
        )
        self.assertEqual(len(requests[1]["messages"]), 3)

    async def test_fifty_slide_outline_uses_exact_schema_and_larger_budget(self) -> None:
        items = [
            {
                "eyebrow": f"{index + 1:02d}",
                "title": f"第 {index + 1} 頁",
                "objective": "說明本頁重點",
                "kind": "cards",
            }
            for index in range(50)
        ]
        items[0]["kind"] = "cover"
        items[-1]["kind"] = "closing"
        outline = {"title": "五十頁大綱", "language": "zh-TW", "items": items}

        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            items_schema = payload["format"]["properties"]["items"]
            self.assertEqual(items_schema["minItems"], 50)
            self.assertEqual(items_schema["maxItems"], 50)
            self.assertEqual(payload["options"]["num_ctx"], 32_000)
            self.assertEqual(payload["options"]["num_predict"], 12_800)
            return httpx.Response(
                200,
                json={
                    "done_reason": "stop",
                    "eval_count": 5000,
                    "message": {"content": json.dumps(outline)},
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
            result = await provider.generate_outline(
                GenerationRequest(topic="測試", slide_count=50)
            )

        self.assertEqual(len(result.items), 50)

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
