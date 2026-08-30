import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import report


def _article(**overrides):
    a = {
        "title": "原題", "title_ja": "日本語タイトル", "intro_score": 4, "verification_score": 5,
        "summary_ja": "何が起きたかの要約。", "reader_question": "本当に速いのか？",
        "test_idea": "手元で計測する。", "metrics": ["所要時間", "成功率"],
        "estimated_time": "2時間", "estimated_cost_level": "low", "url": "https://example.com/a",
    }
    a.update(overrides)
    return a


class RenderReportTests(unittest.TestCase):
    def test_empty_selection_shows_placeholder(self):
        md = report.render_report([("AI検証ネタ", [])], "2026-08-30")
        self.assertIn("2026-08-30", md)
        self.assertIn("ありませんでした", md)

    def test_includes_all_required_fields(self):
        md = report.render_report([("AI検証ネタ", [_article()])], "2026-08-30")
        self.assertIn("日本語タイトル", md)
        self.assertIn("4/5", md)
        self.assertIn("5/5", md)
        self.assertIn("何が起きたかの要約。", md)
        self.assertIn("本当に速いのか？", md)
        self.assertIn("手元で計測する。", md)
        self.assertIn("所要時間、成功率", md)
        self.assertIn("2時間", md)
        self.assertIn("low", md)
        self.assertIn("https://example.com/a", md)

    def test_falls_back_to_original_title_when_no_japanese_title(self):
        md = report.render_report([("AI検証ネタ", [_article(title_ja="")])], "2026-08-30")
        self.assertIn("原題", md)

    def test_numbers_candidates_in_order(self):
        md = report.render_report([("AI検証ネタ", [_article(title_ja="一位"), _article(title_ja="二位")])], "2026-08-30")
        self.assertLess(md.index("1. 一位"), md.index("2. 二位"))

    def test_empty_metrics_shows_placeholder(self):
        md = report.render_report([("AI検証ネタ", [_article(metrics=[])])], "2026-08-30")
        self.assertIn("なし", md)

    def test_shows_merged_sources_when_present(self):
        md = report.render_report([("AI検証ネタ", [_article(merged_sources=["Claude Code Releases", "Hacker News (AI Agent)"])])], "2026-08-30")
        self.assertIn("Claude Code Releases / Hacker News (AI Agent)", md)

    def test_multiple_themes_do_not_overwrite_each_other(self):
        md = report.render_report([
            ("テーマA", [_article(title_ja="A-1件目")]),
            ("テーマB", [_article(title_ja="B-1件目")]),
        ], "2026-08-30")
        self.assertIn("テーマA", md)
        self.assertIn("テーマB", md)
        self.assertIn("A-1件目", md)
        self.assertIn("B-1件目", md)


if __name__ == "__main__":
    unittest.main()
