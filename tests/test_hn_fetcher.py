import json
import sys
import unittest
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import hn_fetcher


def _hit(created_at_i, title="Title", url="https://example.com/a", points=10, num_comments=1, story_id="1"):
    return {
        "created_at_i": created_at_i,
        "title": title,
        "url": url,
        "points": points,
        "num_comments": num_comments,
        "story_id": story_id,
        "objectID": story_id,
    }


def _response(hits):
    return json.dumps({"hits": hits}).encode("utf-8")


class _FakeHTTPResponse:
    def __init__(self, hits):
        self._hits = hits

    def read(self):
        return _response(self._hits)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class HNFetcherTests(unittest.TestCase):
    def _fetch(self, hits, last_seen, source=None):
        source = source or {"name": "HN test", "url": "hn-search://test", "query": "AI agent"}
        with patch.object(hn_fetcher.urllib.request, "urlopen", return_value=_FakeHTTPResponse(hits)):
            return hn_fetcher.fetch_hn(source, last_seen)

    def test_returns_new_articles_after_last_seen(self):
        old = int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp())
        new = int(datetime(2026, 1, 2, tzinfo=timezone.utc).timestamp())
        articles, newest = self._fetch([_hit(new, title="New")], datetime(2026, 1, 1, tzinfo=timezone.utc))
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["title"], "New")
        self.assertEqual(newest, datetime.fromtimestamp(new, tz=timezone.utc))

    def test_first_run_returns_empty_but_advances_watermark(self):
        ts = int(datetime(2026, 1, 2, tzinfo=timezone.utc).timestamp())
        articles, newest = self._fetch([_hit(ts)], None)
        self.assertEqual(articles, [])
        self.assertEqual(newest, datetime.fromtimestamp(ts, tz=timezone.utc))

    def test_min_points_filters_low_score_stories(self):
        ts = int(datetime(2026, 1, 2, tzinfo=timezone.utc).timestamp())
        source = {"name": "HN test", "url": "hn-search://test", "query": "AI agent", "min_points": 20}
        articles, _ = self._fetch([_hit(ts, points=5)], datetime(2026, 1, 1, tzinfo=timezone.utc), source=source)
        self.assertEqual(articles, [])

    def test_missing_url_falls_back_to_discussion_page(self):
        ts = int(datetime(2026, 1, 2, tzinfo=timezone.utc).timestamp())
        articles, _ = self._fetch([_hit(ts, url=None, story_id="42")], datetime(2026, 1, 1, tzinfo=timezone.utc))
        self.assertEqual(articles[0]["url"], "https://news.ycombinator.com/item?id=42")

    def test_network_error_returns_safely_without_raising(self):
        source = {"name": "HN test", "url": "hn-search://test", "query": "AI agent"}
        with patch.object(hn_fetcher.urllib.request, "urlopen", side_effect=urllib.error.URLError("boom")):
            articles, newest = hn_fetcher.fetch_hn(source, datetime(2026, 1, 1, tzinfo=timezone.utc))
        self.assertEqual(articles, [])
        self.assertEqual(newest, datetime(2026, 1, 1, tzinfo=timezone.utc))

    def test_item_id_is_stable_and_reuses_fetcher_scheme(self):
        ts = int(datetime(2026, 1, 2, tzinfo=timezone.utc).timestamp())
        articles, _ = self._fetch([_hit(ts)], datetime(2026, 1, 1, tzinfo=timezone.utc))
        self.assertEqual(len(articles[0]["item_id"]), 64)


if __name__ == "__main__":
    unittest.main()
