import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import selection


def _article(**overrides):
    a = {
        "item_id": "id", "topic_id": "ai-models", "title": "t",
        "decision": "GO", "verification_score": 4, "final_score": 3.0,
        "processed_at": "2026-08-30T04:00:00+00:00",  # JST 13:00
        "published_at": "2026-08-29T00:00:00+00:00",
    }
    a.update(overrides)
    return a


class SelectTop5Tests(unittest.TestCase):
    def test_filters_by_topic_id(self):
        articles = [_article(item_id="a"), _article(item_id="b", topic_id="other")]
        result = selection.select_top5(articles, "ai-models", 3, "2026-08-30")
        self.assertEqual([a["item_id"] for a in result], ["a"])

    def test_excludes_skip_decision(self):
        articles = [_article(item_id="a", decision="SKIP"), _article(item_id="b")]
        result = selection.select_top5(articles, "ai-models", 3, "2026-08-30")
        self.assertEqual([a["item_id"] for a in result], ["b"])

    def test_excludes_below_verification_threshold(self):
        articles = [_article(item_id="a", verification_score=2), _article(item_id="b", verification_score=3)]
        result = selection.select_top5(articles, "ai-models", 3, "2026-08-30")
        self.assertEqual([a["item_id"] for a in result], ["b"])

    def test_excludes_other_days(self):
        articles = [
            _article(item_id="today", processed_at="2026-08-30T04:00:00+00:00"),
            _article(item_id="yesterday", processed_at="2026-08-29T04:00:00+00:00"),
        ]
        result = selection.select_top5(articles, "ai-models", 3, "2026-08-30")
        self.assertEqual([a["item_id"] for a in result], ["today"])

    def test_jst_date_boundary_near_utc_midnight(self):
        # UTC 2026-08-29T22:00:00 = JST 2026-08-30T07:00:00 (the 07:00 JST run)
        articles = [_article(item_id="a", processed_at="2026-08-29T22:00:00+00:00")]
        result = selection.select_top5(articles, "ai-models", 3, "2026-08-30")
        self.assertEqual([a["item_id"] for a in result], ["a"])
        result_prev_day = selection.select_top5(articles, "ai-models", 3, "2026-08-29")
        self.assertEqual(result_prev_day, [])

    def test_sorts_by_final_score_descending_and_caps_at_5(self):
        articles = [_article(item_id=str(i), final_score=float(i)) for i in range(7)]
        result = selection.select_top5(articles, "ai-models", 3, "2026-08-30")
        self.assertEqual([a["item_id"] for a in result], ["6", "5", "4", "3", "2"])

    def test_missing_decision_is_treated_as_not_skip(self):
        articles = [_article(item_id="a")]
        del articles[0]["decision"]
        result = selection.select_top5(articles, "ai-models", 3, "2026-08-30")
        self.assertEqual([a["item_id"] for a in result], ["a"])


if __name__ == "__main__":
    unittest.main()
