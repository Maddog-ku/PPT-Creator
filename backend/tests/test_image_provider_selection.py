import uuid
from types import SimpleNamespace

import pytest

import app.main as main
from app.schemas import GeneratedDeck, GenerationRequest, SlideContent


@pytest.mark.asyncio
async def test_custom_ollama_image_provider_uses_saved_endpoint_and_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image_provider_id = uuid.uuid4()
    config = SimpleNamespace(
        provider="ollama",
        base_url="http://custom-ollama.test",
        model="custom-text-model",
        image_model="custom-image-model",
        encrypted_api_key=None,
    )

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def get(self, model, identifier):
            assert model is main.AIProviderConfig
            assert identifier == image_provider_id
            return config

    class FakeTextProvider:
        model = "text-model"

        async def generate_deck(self, request: GenerationRequest) -> GeneratedDeck:
            return GeneratedDeck(
                title="圖片測試",
                language="zh-TW",
                slides=[
                    SlideContent(eyebrow="C", title="封面", body="開場", kind="cover"),
                    SlideContent(eyebrow="01", title="內容", body="重點", kind="cards"),
                    SlideContent(eyebrow="E", title="結尾", body="收尾", kind="closing"),
                ],
            )

    calls: list[tuple[str, str, str]] = []

    class FakeOllamaImageProvider:
        def __init__(self, *, base_url: str, model: str, timeout_seconds: float):
            self.base_url = base_url
            self.model = model

        async def generate_image(self, prompt: str, *, image_model: str) -> str:
            calls.append((self.base_url, self.model, image_model))
            return "data:image/png;base64,aW1hZ2U="

    monkeypatch.setattr(main, "SessionLocal", lambda: FakeSession())
    monkeypatch.setattr(main, "get_ollama_provider", lambda: FakeTextProvider())
    monkeypatch.setattr(main, "OllamaProvider", FakeOllamaImageProvider)

    deck, _, _ = await main._generate_deck(
        GenerationRequest(
            topic="圖片測試",
            slide_count=3,
            generate_images=True,
            image_provider_id=image_provider_id,
            image_count=1,
        )
    )

    assert calls == [
        ("http://custom-ollama.test", "custom-text-model", "custom-image-model")
    ]
    assert deck.slides[1].image_data == "data:image/png;base64,aW1hZ2U="
