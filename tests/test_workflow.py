from pathlib import Path
import unittest



ROOT = Path(__file__).resolve().parents[1]


class WorkflowTests(unittest.TestCase):
    def test_workflow_has_expected_triggers_and_actions(self):
        content = (ROOT / ".github" / "workflows" / "monitor.yml").read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", content)
        # JST 13:00 / 21:00 / 翌07:00 を UTC で直接指定する。
        self.assertIn('cron: "0 4,12,22 * * *"', content)
        self.assertNotIn("*/5 * * * *", content)
        self.assertNotIn("push:", content)
        self.assertIn("contents: write", content)
        self.assertIn("actions/upload-pages-artifact@v3", content)
        self.assertIn("actions/deploy-pages@v4", content)
        self.assertIn("secrets.GEMINI_API_KEY", content)
        self.assertIn("cancel-in-progress: false", content)

    def test_run_is_not_gated_by_a_time_window(self):
        """起動したら必ず処理する。時刻ゲートの痕跡を残さない。"""
        content = (ROOT / ".github" / "workflows" / "monitor.yml").read_text(encoding="utf-8")
        self.assertNotIn("MONITOR_SCHEDULED", content)
        self.assertFalse((ROOT / "src" / "schedule.py").exists())
        main_source = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
        self.assertNotIn("MONITOR_SCHEDULED", main_source)
        self.assertNotIn("due_slot", main_source)


if __name__ == "__main__":
    unittest.main()
