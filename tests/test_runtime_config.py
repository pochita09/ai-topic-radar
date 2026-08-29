"""config.yaml をソース一覧の正とし、KV は ON/OFF だけを預かることを確認する。"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import runtime_config


def base_config() -> dict:
    return {
        "themes": [
            {
                "topic_id": "ai-models",
                "name": "AIモデル系",
                "threshold": 6,
                "sources": [
                    {"source_id": "openai-news", "name": "OpenAI News", "url": "https://example.com/openai.xml"},
                    {"source_id": "deepmind-blog", "name": "Google DeepMind Blog", "url": "https://example.com/deepmind.xml"},
                ],
            }
        ],
        "run": {"keep_below_threshold": True, "read_dim_enabled": True},
    }


def sources_of(config: dict) -> dict:
    return {source["source_id"]: source.get("enabled", True) for source in config["themes"][0]["sources"]}


class SourceMergeTests(unittest.TestCase):
    def test_missing_sources_in_kv_stay_enabled(self):
        """KVが1本しか持っていなくても config.yaml の2本が残る（Phase 0 で起きた事故の再発防止）。"""
        settings = {"topics": {"ai-models": {"sources": {"openai-news": {"name": "x", "url": "y", "enabled": True}}}}}
        merged = runtime_config.apply_settings(base_config(), settings)
        self.assertEqual(sources_of(merged), {"openai-news": True, "deepmind-blog": True})

    def test_kv_disables_a_source(self):
        settings = {"topics": {"ai-models": {"sources": {"deepmind-blog": {"name": "x", "url": "y", "enabled": False}}}}}
        merged = runtime_config.apply_settings(base_config(), settings)
        self.assertEqual(sources_of(merged), {"openai-news": True, "deepmind-blog": False})

    def test_boolean_shorthand_is_accepted(self):
        settings = {"topics": {"ai-models": {"sources": {"openai-news": False}}}}
        merged = runtime_config.apply_settings(base_config(), settings)
        self.assertEqual(sources_of(merged), {"openai-news": False, "deepmind-blog": True})

    def test_unknown_source_in_kv_is_ignored(self):
        """config.yaml に無いソースは採用しない。URLの正は常にリポジトリ側。"""
        settings = {"topics": {"ai-models": {"sources": {"user-abc": {"name": "n", "url": "https://e.com/f.xml", "enabled": True}}}}}
        merged = runtime_config.apply_settings(base_config(), settings)
        self.assertEqual(sources_of(merged), {"openai-news": True, "deepmind-blog": True})

    def test_kv_cannot_rewrite_a_source_url(self):
        settings = {"topics": {"ai-models": {"sources": {"openai-news": {"name": "乗っ取り", "url": "https://evil.example/f.xml", "enabled": True}}}}}
        merged = runtime_config.apply_settings(base_config(), settings)
        source = merged["themes"][0]["sources"][0]
        self.assertEqual(source["url"], "https://example.com/openai.xml")
        self.assertEqual(source["name"], "OpenAI News")


class RunSettingsTests(unittest.TestCase):
    def test_run_times_are_ignored(self):
        """実行時刻はワークフローの cron が正。KVの値は取り込まない。"""
        merged = runtime_config.apply_settings(base_config(), {"run": {"times": ["01:00"]}})
        self.assertNotIn("times", merged["run"])

    def test_settings_payload_has_no_times(self):
        self.assertNotIn("times", runtime_config.settings_payload(base_config())["run"])

    def test_known_boolean_settings_still_apply(self):
        merged = runtime_config.apply_settings(base_config(), {"run": {"keep_below_threshold": False}})
        self.assertFalse(merged["run"]["keep_below_threshold"])

    def test_display_name_and_threshold_still_apply(self):
        settings = {"topics": {"ai-models": {"display_name": "別名", "criteria": "基準", "threshold": 9}}}
        merged = runtime_config.apply_settings(base_config(), settings)
        theme = merged["themes"][0]
        self.assertEqual(theme["display_name"], "別名")
        self.assertEqual(theme["filter_prompt"], "基準")
        self.assertEqual(theme["threshold"], 9)


class FetchSettingsTests(unittest.TestCase):
    def test_request_sends_a_browser_user_agent(self):
        """Python-urllib のままだと Cloudflare error 1010 で 403 になる。"""
        captured = {}

        class FakeResponse:
            def read(self):
                return b'{"config": {}}'

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def fake_urlopen(request, timeout=None):
            captured["user_agent"] = request.get_header("User-agent")
            return FakeResponse()

        with patch.object(runtime_config.urllib.request, "urlopen", fake_urlopen):
            runtime_config.fetch_settings("https://worker.example")

        self.assertIsNotNone(captured["user_agent"])
        self.assertNotIn("Python-urllib", captured["user_agent"])


if __name__ == "__main__":
    unittest.main()
