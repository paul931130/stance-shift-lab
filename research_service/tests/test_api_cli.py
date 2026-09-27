"""The Python API and the interactive stance-shift command, with the built-in demo provider."""
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from research_service import api
from research_service.cli import main
from research_service.demo import DEMO_MODEL, demo_dataset, demo_model


class DemoResearch(api.StanceShiftResearch):
    """The real API with the deterministic demo provider and a pre-loaded dataset."""

    def __init__(self, data_dir=None, model=None):
        super().__init__(data_dir=data_dir, model=model or DEMO_MODEL, model_call=demo_model)

    def collect(self, ticker, analysis_date, **_):
        return {"id": self.store.add_dataset(demo_dataset())}


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_run_completes_all_four_groups_and_stores_an_auditable_job(self):
        research = DemoResearch(self.tmp.name)
        nodes = []
        result = research.run("NVDA", "2024-12-31", progress=lambda **event: nodes.append(event.get("node")))
        self.assertEqual(result["status"], "complete")
        self.assertEqual(set(result["decisions"]), set("ABCD"))
        self.assertTrue(result["backtest"])
        self.assertEqual(nodes[-1], "backtest_and_memory_write")
        # Same store as the web service: the job is listed with its full trace.
        stored = research.store.get(result["job_id"])
        self.assertTrue(stored["state"]["finished"])
        self.assertEqual(stored["config"]["protocol"]["model"], DEMO_MODEL)

    def test_start_does_not_leave_the_job_for_a_web_worker_to_claim(self):
        research = DemoResearch(self.tmp.name)
        job_id = research.start("NVDA", "2024-12-31")
        self.assertIsNone(research.store.claim())
        self.assertEqual(research.resume(job_id)["status"], "complete")

    def test_failed_step_is_saved_and_resumable(self):
        down = {"on": True}

        def flaky(*args, **kwargs):
            # Research agents fall back to source extracts; a decision call cannot.
            if down["on"] and "Return JSON: summary" not in json.dumps(args[1] if len(args) > 1 else kwargs):
                raise RuntimeError("provider down")
            return demo_model(*args, **kwargs)

        research = DemoResearch(self.tmp.name)
        research.engine.model_call = flaky
        with self.assertRaises(api.ResearchRunError) as caught:
            research.run("NVDA", "2024-12-31")
        self.assertEqual(research.store.get(caught.exception.job_id)["status"], "paused")
        down["on"] = False
        self.assertEqual(research.resume(caught.exception.job_id)["status"], "complete")


class InteractiveCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = {"RESEARCH_DATA_DIR": self.tmp.name, "STANCE_SHIFT_MODEL": DEMO_MODEL,
               "SEC_USER_AGENT": "Test test@example.com", "FRED_API_KEY": "x", "ALPHA_VANTAGE_API_KEY": "x"}
        patcher = patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        for name in ("STANCE_SHIFT_TICKER", "STANCE_SHIFT_DATE"):
            os.environ.pop(name, None)

    def run_cli(self, answers, argv=()):
        output, answers, self.prompts = io.StringIO(), list(answers), []

        def fake_input(prompt=""):
            self.prompts.append(prompt)
            return answers.pop(0)

        with patch.object(api, "StanceShiftResearch", DemoResearch), \
             patch("builtins.input", side_effect=fake_input), \
             patch("importlib.util.find_spec", return_value=None), redirect_stdout(output):
            code = main(list(argv))
        return code, output.getvalue()

    def test_no_arguments_asks_questions_runs_and_remembers_answers(self):
        code, output = self.run_cli(["msft", "MSFT", "2024-12-31"])
        self.assertEqual(code, 0, output)
        self.assertIn("請輸入其中之一", output)  # lower-case ticker is rejected, then asked again
        self.assertIn("D 立場交換辯論", output)
        self.assertIn("實驗 ID", output)
        with open(os.path.join(self.tmp.name, "private", "cli_last.json"), encoding="utf-8") as handle:
            remembered = json.load(handle)
        self.assertEqual((remembered["ticker"], remembered["date"]), ("MSFT", "2024-12-31"))
        # Next run: Enter accepts both remembered answers.
        code, output = self.run_cli(["", ""])
        self.assertEqual(code, 0, output)
        self.assertIn("股票 [MSFT]: ", self.prompts)

    def test_scripted_run_prints_json(self):
        code, output = self.run_cli([], ["run", "NVDA", "2024-12-31", "--model", DEMO_MODEL, "--json"])
        self.assertEqual(code, 0, output)
        self.assertEqual(set(json.loads(output)["decisions"]), set("ABCD"))


class EnvFileTests(unittest.TestCase):
    def test_env_file_fills_missing_values_only_and_skips_docker_ollama_host(self):
        from research_service.interactive import load_env_files

        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, ".env")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("# comment\nGEMINI_API_KEY='from-file'\nFRED_API_KEY=from-file\n"
                             "OLLAMA_BASE_URL=http://host.docker.internal:11434\nEMPTY=\n")
            with patch.dict(os.environ, {"FRED_API_KEY": "already-set"}, clear=False):
                for name in ("GEMINI_API_KEY", "OLLAMA_BASE_URL", "EMPTY"):
                    os.environ.pop(name, None)
                with patch("research_service.interactive.Path.exists", return_value=False):
                    load_env_files([path])
                self.assertEqual(os.environ["GEMINI_API_KEY"], "from-file")
                self.assertEqual(os.environ["FRED_API_KEY"], "already-set")
                self.assertNotIn("OLLAMA_BASE_URL", os.environ)
                self.assertNotIn("EMPTY", os.environ)


if __name__ == "__main__":
    unittest.main()
