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

    def test_start_creates_the_job_already_paused(self):
        research = DemoResearch(self.tmp.name)
        job = research.store.get(research.start("NVDA", "2024-12-31"))
        self.assertEqual((job["status"], job["wants_run"]), ("paused", 0))

    def test_resume_refuses_cancelled_and_worker_owned_jobs(self):
        research = DemoResearch(self.tmp.name)
        cancelled = research.start("NVDA", "2024-12-31")
        research.store.control(cancelled, "cancel")
        with self.assertRaisesRegex(ValueError, "取消"):
            research.resume(cancelled)
        running = research.start("NVDA", "2024-12-31", voting_samples=5)
        research.store.control(running, "resume")
        self.assertEqual(research.store.claim()["id"], running)  # the web worker owns it now
        with self.assertRaisesRegex(ValueError, "worker"):
            research.resume(running)

    def test_only_one_process_can_hold_a_job(self):
        research = DemoResearch(self.tmp.name)
        job_id = research.start("NVDA", "2024-12-31")
        _, owner = research._take_over(job_id)
        with self.assertRaisesRegex(ValueError, "其他程序"):
            research._take_over(job_id)  # a second stance-shift resume
        research.store.control(job_id, "resume")  # 繼續 pressed in the web UI
        self.assertIsNone(research.store.claim())
        from research_service.storage import JobLeaseLost
        job = research.store.get(job_id)
        with self.assertRaises(JobLeaseLost):
            research.store.save_step(job_id, job["state"], owner="cli:someone-else")
        research.store.release(job_id, owner)
        self.assertEqual(research.store.get(job_id)["owner"], "")

    def test_a_killed_cli_lease_can_be_taken_over_after_it_goes_stale(self):
        research = DemoResearch(self.tmp.name)
        job_id = research.start("NVDA", "2024-12-31")
        research._take_over(job_id)
        with research.store.connect() as db:
            db.execute("UPDATE jobs SET updated_at='2000-01-01T00:00:00+00:00' WHERE id=?", (job_id,))
        self.assertEqual(research.resume(job_id)["status"], "complete")

    def test_pausing_in_the_web_ui_stops_a_cli_run(self):
        research = DemoResearch(self.tmp.name)
        job_id = research.start("NVDA", "2024-12-31")

        def pause_then_answer(protocol, messages, **kwargs):
            research.store.control(job_id, "pause")
            return demo_model(protocol, messages, **kwargs)

        research.engine.model_call = pause_then_answer
        with self.assertRaisesRegex(api.ResearchRunError, "暫停"):
            research.resume(job_id)
        job = research.store.get(job_id)
        self.assertEqual((job["status"], job["owner"]), ("paused", ""))
        self.assertTrue(job["steps"] or job["state"]["research"])  # the finished step was kept

    def test_resume_takes_a_queued_job_away_from_the_worker(self):
        research = DemoResearch(self.tmp.name)
        job_id = research.start("NVDA", "2024-12-31")
        research.store.control(job_id, "resume")  # e.g. 繼續 pressed in the web UI
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


class DemoModeTests(unittest.TestCase):
    """RESEARCH_DEMO_MODE=true lets the CLI and API run end to end with no keys or network."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = patch.dict(os.environ, {"RESEARCH_DEMO_MODE": "true", "RESEARCH_DATA_DIR": self.tmp.name})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_api_runs_the_synthetic_case_and_refuses_other_cases(self):
        research = api.StanceShiftResearch()
        self.assertTrue(research.demo_mode)
        self.assertEqual(research.run("NVDA", "2024-12-31")["model"], DEMO_MODEL)
        with self.assertRaisesRegex(ValueError, "展示模式"):
            research.collect("MSFT", "2024-12-31")

    def test_cli_without_arguments_asks_nothing(self):
        output = io.StringIO()
        with patch("builtins.input", side_effect=AssertionError("demo mode must not ask")), redirect_stdout(output):
            self.assertEqual(main([]), 0)
        self.assertIn("展示模式", output.getvalue())
        self.assertIn("D 立場交換辯論", output.getvalue())


class EnvFileTests(unittest.TestCase):
    def test_choosing_a_cloud_model_keeps_the_shared_gputw_setting(self):
        from research_service.interactive import Remembered, choose_model
        from research_service.settings import Settings

        class Answers:
            fancy = False

            def __init__(self, *values):
                self.values = list(values)

            def header(self, *_):
                pass

            def select(self, _question, _choices, _default):
                return self.values.pop(0)

            def secret(self, _question, current):
                return current

        with tempfile.TemporaryDirectory() as directory, \
             patch.dict(os.environ, {"GEMINI_API_KEY": "k", "STANCE_SHIFT_MODEL": ""}):
            settings = Settings(directory)
            settings.save({"GPUTW_OLLAMA_BASE_URL": "https://gpu.example/ollama"})
            model = choose_model(settings, Remembered(directory), Answers("1", "1", "gemini/gemini-2.5-flash"))
            self.assertEqual(model, "gemini/gemini-2.5-flash")
            self.assertEqual(os.environ["GPUTW_OLLAMA_BASE_URL"], "https://gpu.example/ollama")
            self.assertEqual(Settings(directory)._read().get("GPUTW_OLLAMA_BASE_URL"), "https://gpu.example/ollama")

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
