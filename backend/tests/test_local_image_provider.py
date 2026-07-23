import json
import unittest

import httpx

from app.ai import LocalImageProvider


class LocalImageProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_generates_image_with_stable_diffusion_webui_api(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/sdapi/v1/txt2img")
            payload = json.loads(request.content)
            self.assertEqual(payload["width"], 1024)
            self.assertEqual(payload["height"], 576)
            self.assertEqual(
                payload["override_settings"]["sd_model_checkpoint"],
                "local-checkpoint",
            )
            self.assertTrue(payload["override_settings_restore_afterwards"])
            return httpx.Response(200, json={"images": ["aW1hZ2U="]})

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="http://stable-diffusion.test",
        ) as client:
            provider = LocalImageProvider(
                base_url="http://stable-diffusion.test",
                model="local-checkpoint",
                client=client,
            )
            image = await provider.generate_image("A clean chart")
        self.assertEqual(image, "data:image/png;base64,aW1hZ2U=")

    async def test_releases_checkpoint_memory(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/sdapi/v1/unload-checkpoint")
            self.assertEqual(request.method, "POST")
            return httpx.Response(200, json={})

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="http://stable-diffusion.test",
        ) as client:
            provider = LocalImageProvider(
                base_url="http://stable-diffusion.test",
                model="local-checkpoint",
                client=client,
            )
            await provider.release_model()


if __name__ == "__main__":
    unittest.main()
