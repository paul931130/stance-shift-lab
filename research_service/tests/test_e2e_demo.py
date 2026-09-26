"""Browser smoke test: run one full demo experiment through the real UI.

Starts the service in demo mode (synthetic data, deterministic provider, no
network) and drives it with headless Chromium. Skipped unless Playwright and
its Chromium build are installed:

    pip install playwright && python -m playwright install chromium
"""
import os
import socket
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

try:
    from playwright.sync_api import Error as PlaywrightError, sync_playwright
except ImportError:  # optional dev dependency
    sync_playwright = None

import uvicorn

from research_service.app import create_app
from research_service.storage import Store


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@unittest.skipIf(sync_playwright is None, "Playwright is not installed")
class DemoExperimentE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.env = patch.dict(os.environ, {"RESEARCH_DEMO_MODE": "true", "RESEARCH_ACCESS_KEY": "", "RESEARCH_REMOTE": "false"})
        cls.env.start()
        port = free_port()
        cls.base = f"http://127.0.0.1:{port}"
        cls.server = uvicorn.Server(uvicorn.Config(create_app(Store(cls.tmp.name)), host="127.0.0.1",
                                                   port=port, log_level="warning"))
        cls.thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.thread.start()
        deadline = time.monotonic() + 20
        while not cls.server.started:
            if time.monotonic() > deadline:
                raise RuntimeError("demo server did not start")
            time.sleep(.05)
        cls.playwright = sync_playwright().start()
        try:
            cls.browser = cls.playwright.chromium.launch()
        except PlaywrightError as error:
            cls.playwright.stop()
            cls.tearDownServer()
            raise unittest.SkipTest(f"Chromium for Playwright is not installed: {error}")

    @classmethod
    def tearDownServer(cls):
        cls.server.should_exit = True
        cls.thread.join(10)
        cls.env.stop()
        cls.tmp.cleanup()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.tearDownServer()

    def test_full_demo_experiment_through_the_ui(self):
        page = self.browser.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)

        page.goto(self.base + "/")
        # The live pipeline map renders and the demo snapshot opens step 2.
        page.wait_for_selector(".flow-svg .flow-node")
        page.wait_for_selector('[data-panel="experiment"]:not([hidden])')
        # The server-side preflight approves the demo case before the run button unlocks.
        page.wait_for_selector("#experiment-guard.ready")
        self.assertTrue(page.is_enabled("#run-button"))

        page.click("#run-button")
        # The job runs to completion; finishing moves the UI to the statistics step.
        page.wait_for_selector('[data-panel="stats"]:not([hidden])', timeout=60_000)
        page.wait_for_selector("#statistics .stats-substep", timeout=20_000)
        self.assertIn("同協議研究比較", page.inner_text("#statistics"))

        # Step 3 shows the finished run, and the map reports every model output.
        page.click('.tabs [data-tab-button="runs"]')
        self.assertIn("已完成", page.inner_text("#run-detail h2"))
        outputs = page.inner_text("#run-detail .run-progress strong")
        done, total = outputs.split("/")
        self.assertEqual(done.strip(), total.strip())
        self.assertGreater(page.locator(".flow-node.is-done").count(), 0)

        self.assertEqual(errors, [])
        page.close()


if __name__ == "__main__":
    unittest.main()
