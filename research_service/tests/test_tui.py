"""The terminal dashboard and question helpers used by the interactive stance-shift."""
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from rich.console import Console

from research_service import api, tui
from research_service.interactive import planned_calls
from research_service.demo import DEMO_MODEL, demo_dataset, demo_model


def render_text(renderable, width=140, height=40):
    console = Console(file=io.StringIO(), width=width, height=height, force_terminal=False, color_system=None)
    console.print(renderable, height=height)
    return console.file.getvalue()


class DashboardTests(unittest.TestCase):
    def test_full_demo_run_updates_every_panel(self):
        with tempfile.TemporaryDirectory() as folder:
            research = api.StanceShiftResearch(data_dir=folder, model=DEMO_MODEL, model_call=demo_model)
            dataset_id = research.store.add_dataset(demo_dataset())
            job_id = research.start("NVDA", "2024-12-31", dataset_id=dataset_id)
            board = tui.Dashboard("NVDA · 2024-12-31", planned_calls())
            board.update("collect", stage="collecting")
            self.assertIn("執行中", render_text(board.render()))
            board.update("collect", agents={d: {"status": "complete", "message": "ok"} for d in tui.DOMAIN_NAMES})
            seen_running = []

            def update(phase, **event):
                board.update(phase, **event)
                if event.get("node") == "neutral_report_locked":
                    seen_running.append(sum(c["status"] == "running" for c in board.calls.values()))

            result = research.resume(job_id, progress=update)
        text = render_text(board.render())
        self.assertEqual(seen_running, [10])  # A, all seven B votes, first C and D rounds
        self.assertTrue(all(call["status"] == "done" for call in board.calls.values()))
        for label in ("Agent 狀態", "四組決策", "D 立場交換辯論", "R2 看空", "第 7 票", "裁決", "22/22"):
            self.assertIn(label, text)
        self.assertNotIn("等待", text)
        table = render_text(tui.result_table(result))
        self.assertIn("D 立場交換辯論", table)
        self.assertIn("方向正確", table)

    def test_degraded_research_and_missing_data_are_flagged(self):
        board = tui.Dashboard("x", planned_calls())
        board.update("collect", agents={"macro": {"status": "needs_configuration", "message": "未設定 FRED_API_KEY"}})
        board.update("run", node="parallel_research_agents[sentiment]",
                     research={"sentiment": {"status": "degraded"}, "macro": {"status": "missing"}})
        text = render_text(board.render())
        self.assertIn("! 注意", text)
        self.assertIn("— 無資料", text)
        self.assertIn("未設定 FRED_API_KEY", text)


class PrompterTests(unittest.TestCase):
    def test_plain_mode_validates_choices_and_keeps_defaults(self):
        prompter = tui.Prompter(fancy=False)
        output = io.StringIO()  # the hint is Chinese; Windows CI's cp1252 stdout cannot print it
        with patch("builtins.input", side_effect=["ZZZ", "MSFT", ""]), redirect_stdout(output):
            self.assertEqual(prompter.select("股票", [("NVDA", "NVDA"), ("MSFT", "MSFT")], "NVDA"), "MSFT")
            self.assertTrue(prompter.confirm("開始？", True))
        self.assertIn("請輸入其中之一", output.getvalue())

    def test_secret_keeps_the_current_value_on_enter(self):
        with patch("research_service.tui.getpass", return_value=""):
            self.assertEqual(tui.Prompter(fancy=False).secret("key", "kept"), "kept")

    def test_fancy_mode_uses_arrow_key_questions(self):
        prompter = tui.Prompter(fancy=True)
        with patch("questionary.select") as select:
            select.return_value.ask.return_value = "MSFT"
            self.assertEqual(prompter.select("股票", [("NVDA", "NVDA"), ("MSFT", "MSFT")], "NVDA"), "MSFT")
        with patch("questionary.confirm") as confirm, self.assertRaises(KeyboardInterrupt):
            confirm.return_value.ask.return_value = None  # Ctrl+C inside questionary
            prompter.confirm("開始？")

    def test_non_terminal_is_detected(self):
        with patch("sys.stdin", io.StringIO()):
            self.assertFalse(tui.is_interactive())


if __name__ == "__main__":
    unittest.main()
