import importlib
import json
import sys
import tempfile
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch


# The project dependencies are intentionally stubbed here so these core tests can
# run even before a non-engineer installs requirements.txt locally.
sys.modules.setdefault("feedparser", types.SimpleNamespace(parse=lambda url: None))
google_module = sys.modules.setdefault("google", types.ModuleType("google"))
if not hasattr(google_module, "genai"):
    google_module.genai = types.SimpleNamespace(Client=lambda api_key: None)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import ai_filter
import archive
import fetcher
from fetcher import make_item_id


class ItemIdTests(unittest.TestCase):
    def test_item_id_ignores_tracking_and_harmless_title_variation(self):
        published = datetime(2026, 1, 1, tzinfo=timezone.utc)
        tracked = make_item_id("https://EXAMPLE.com/article/?utm_source=rss#top", " A   Title ", published)
        canonical = make_item_id("https://example.com/article", "a title", published)
        self.assertEqual(tracked, canonical)

    def test_broken_feed_returns_safely_without_raising(self):
        broken_feed = types.SimpleNamespace(bozo=True, entries=[], bozo_exception=ValueError("bad rss"))
        with patch.object(fetcher.feedparser, "parse", return_value=broken_feed):
            articles, newest = fetcher.fetch_feed(
                {"name": "Broken", "url": "https://example.invalid/rss"},
                datetime(2026, 1, 1, tzinfo=timezone.utc),
            )
        self.assertEqual(articles, [])
        self.assertEqual(newest, datetime(2026, 1, 1, tzinfo=timezone.utc))


class ArchiveTests(unittest.TestCase):
    def test_archive_upserts_by_item_id_and_remains_valid_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "articles.json"
            first = {"item_id": "one", "processed_at": "2026-01-01T00:00:00+00:00", "title": "first"}
            replacement = {"item_id": "one", "processed_at": "2026-01-02T00:00:00+00:00", "title": "updated"}
            with patch.object(archive, "ARCHIVE_FILE", path):
                archive.save_articles([], [first])
                saved = archive.save_articles(archive.load_articles(), [replacement])
                self.assertEqual(len(saved), 1)
                self.assertEqual(saved[0]["title"], "updated")
                self.assertEqual(json.loads(path.read_text(encoding="utf-8"))[0]["item_id"], "one")


def _theme(**overrides):
    theme = {"topic_id": "test", "intro_criteria": "intro", "verification_criteria": "verification"}
    theme.update(overrides)
    return theme


def _result(**overrides):
    result = {
        "index": 1, "title_ja": "短い日本語見出し", "summary_ja": "有効な要約", "tags": ["API"],
        "intro_score": 4, "verification_score": 3, "reader_question": "本当に速いのか？",
        "test_idea": "手元で計測する", "metrics": ["所要時間"], "estimated_time": "30分",
        "estimated_cost_level": "low", "decision": "GO", "reason": "強いデモがある",
    }
    result.update(overrides)
    return result


class GeminiValidationTests(unittest.TestCase):
    def test_keeps_short_japanese_title_when_gemini_returns_one(self):
        response = types.SimpleNamespace(text=json.dumps({"results": [_result()]}))
        client = types.SimpleNamespace(models=types.SimpleNamespace(generate_content=lambda **kwargs: response))
        with patch.object(ai_filter.genai, "Client", return_value=client), patch.dict("os.environ", {"GEMINI_API_KEY": "test"}):
            result = ai_filter.filter_and_summarize([
                {"item_id": "one", "title": "original title", "url": "https://example.com/1", "summary": "", "published_at": "2026-01-01T00:00:00+00:00"},
            ], _theme(), "test-model")
        self.assertEqual(result[0]["title_ja"], "短い日本語見出し")

    def test_invalid_single_result_does_not_abort_valid_results(self):
        response = types.SimpleNamespace(text=json.dumps({"results": [
            _result(index=1),
            _result(index=2, verification_score="bad"),
        ]}))
        client = types.SimpleNamespace(models=types.SimpleNamespace(generate_content=lambda **kwargs: response))
        with patch.object(ai_filter.genai, "Client", return_value=client), patch.dict("os.environ", {"GEMINI_API_KEY": "test"}):
            result = ai_filter.filter_and_summarize([
                {"item_id": "one", "title": "one", "url": "https://example.com/1", "summary": "", "published_at": "2026-01-01T00:00:00+00:00"},
                {"item_id": "two", "title": "two", "url": "https://example.com/2", "summary": "", "published_at": "2026-01-01T00:00:00+00:00"},
            ], _theme(), "test-model")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["topic_id"], "test")
        self.assertEqual(result[0]["intro_score"], 4)

    def test_final_score_uses_theme_weights(self):
        response = types.SimpleNamespace(text=json.dumps({"results": [_result(intro_score=4, verification_score=5)]}))
        client = types.SimpleNamespace(models=types.SimpleNamespace(generate_content=lambda **kwargs: response))
        with patch.object(ai_filter.genai, "Client", return_value=client), patch.dict("os.environ", {"GEMINI_API_KEY": "test"}):
            result = ai_filter.filter_and_summarize([
                {"item_id": "one", "title": "one", "url": "https://example.com/1", "summary": "", "published_at": "2026-01-01T00:00:00+00:00"},
            ], _theme(intro_weight=0.4, verification_weight=0.6), "test-model")
        self.assertAlmostEqual(result[0]["final_score"], 4 * 0.4 + 5 * 0.6)

    def test_skip_decision_is_kept_with_zero_scores(self):
        response = types.SimpleNamespace(text=json.dumps({"results": [
            _result(intro_score=0, verification_score=0, decision="SKIP", reason="人事ニュースのため除外"),
        ]}))
        client = types.SimpleNamespace(models=types.SimpleNamespace(generate_content=lambda **kwargs: response))
        with patch.object(ai_filter.genai, "Client", return_value=client), patch.dict("os.environ", {"GEMINI_API_KEY": "test"}):
            result = ai_filter.filter_and_summarize([
                {"item_id": "one", "title": "one", "url": "https://example.com/1", "summary": "", "published_at": "2026-01-01T00:00:00+00:00"},
            ], _theme(), "test-model")
        self.assertEqual(result[0]["decision"], "SKIP")
        self.assertEqual(result[0]["final_score"], 0)


if __name__ == "__main__":
    unittest.main()
