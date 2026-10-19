import asyncio
import json
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from research_service.web.datasets import build_router


class DatasetImportTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.store = SimpleNamespace(add_dataset=Mock(return_value="saved"))
        self.app = FastAPI()
        self.app.include_router(build_router(SimpleNamespace(store=self.store)))

        @self.app.exception_handler(ValueError)
        async def invalid(request, error):
            return JSONResponse({"detail": str(error)}, status_code=422)

        @self.app.get("/ping")
        async def ping():
            return {"ok": True}

    def client(self):
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://test")

    async def test_rejects_non_object_and_invalid_json(self):
        async with self.client() as client:
            for body in (b"[]", b"null", b"123", b"{", b"\xff"):
                response = await client.post("/api/datasets/import", content=body)
                self.assertEqual(response.status_code, 422)
        self.store.add_dataset.assert_not_called()

    async def test_stream_limit_stops_before_consuming_remaining_chunks(self):
        consumed = []

        async def chunks():
            for size in (3_000_000, 3_000_001, 1):
                consumed.append(size)
                yield b" " * size

        async with self.client() as client:
            response = await client.post("/api/datasets/import", content=chunks())
        self.assertEqual(response.status_code, 413)
        self.assertEqual(consumed, [3_000_000, 3_000_001])
        self.store.add_dataset.assert_not_called()

    async def test_finbert_does_not_block_other_async_requests(self):
        entered, release = threading.Event(), threading.Event()

        def infer(data):
            entered.set()
            if not release.wait(3):
                raise AssertionError("event loop did not serve the concurrent request")
            return data

        with patch("research_service.web.datasets.validate_dataset", side_effect=lambda data: data), \
                patch("research_service.web.datasets.score_sentiment_finbert", side_effect=infer):
            async with self.client() as client:
                task = asyncio.create_task(client.post("/api/datasets/import?use_finbert=true",
                                                       content=json.dumps({"ticker": "NVDA", "kind": "test"})))
                try:
                    self.assertTrue(await asyncio.to_thread(entered.wait, 2))
                    response = await asyncio.wait_for(client.get("/ping"), .5)
                    self.assertEqual(response.json(), {"ok": True})
                finally:
                    release.set()
                imported = await task
        self.assertEqual(imported.json(), {"id": "saved", "finbert_applied": True})
        self.store.add_dataset.assert_called_once()


if __name__ == "__main__":
    unittest.main()
