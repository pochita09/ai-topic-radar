import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import theme_merge


def _article(**overrides):
    a = {
        "item_id": "id", "title": "Claude Code releases v2.1", "title_ja": "",
        "source": "Claude Code Releases", "final_score": 3.0,
        "published_at": "2026-08-29T00:00:00+00:00",
    }
    a.update(overrides)
    return a


class FindCandidatePairsTests(unittest.TestCase):
    def test_similar_titles_within_date_window_are_paired(self):
        articles = [
            _article(item_id="a", title="Claude Code v2.1 released"),
            _article(item_id="b", title="Claude Code v2.1 is released today"),
        ]
        pairs = theme_merge.find_candidate_pairs(articles)
        self.assertEqual(pairs, [(0, 1)])

    def test_dissimilar_titles_are_not_paired(self):
        articles = [
            _article(item_id="a", title="Claude Code v2.1 released"),
            _article(item_id="b", title="I built a headless browser in Rust"),
        ]
        pairs = theme_merge.find_candidate_pairs(articles)
        self.assertEqual(pairs, [])

    def test_titles_too_far_apart_in_date_are_not_paired(self):
        articles = [
            _article(item_id="a", title="Claude Code v2.1 released", published_at="2026-08-01T00:00:00+00:00"),
            _article(item_id="b", title="Claude Code v2.1 released again", published_at="2026-08-29T00:00:00+00:00"),
        ]
        pairs = theme_merge.find_candidate_pairs(articles, days_window=3)
        self.assertEqual(pairs, [])


class JudgePairsWithLLMTests(unittest.TestCase):
    def test_parses_llm_response_into_bool_list(self):
        articles = [_article(item_id="a"), _article(item_id="b"), _article(item_id="c")]
        pairs = [(0, 1), (1, 2)]
        response = types.SimpleNamespace(text=json.dumps({"results": [
            {"index": 1, "same_topic": True},
            {"index": 2, "same_topic": False},
        ]}))
        client = types.SimpleNamespace(models=types.SimpleNamespace(generate_content=lambda **kwargs: response))
        with patch.object(theme_merge.genai, "Client", return_value=client), patch.dict("os.environ", {"GEMINI_API_KEY": "test"}):
            result = theme_merge.judge_pairs_with_llm(articles, pairs, "test-model")
        self.assertEqual(result, [True, False])

    def test_missing_index_defaults_to_false(self):
        articles = [_article(item_id="a"), _article(item_id="b")]
        pairs = [(0, 1)]
        response = types.SimpleNamespace(text=json.dumps({"results": []}))
        client = types.SimpleNamespace(models=types.SimpleNamespace(generate_content=lambda **kwargs: response))
        with patch.object(theme_merge.genai, "Client", return_value=client), patch.dict("os.environ", {"GEMINI_API_KEY": "test"}):
            result = theme_merge.judge_pairs_with_llm(articles, pairs, "test-model")
        self.assertEqual(result, [False])

    def test_empty_pairs_skips_llm_call(self):
        with patch.object(theme_merge.genai, "Client") as mock_client:
            result = theme_merge.judge_pairs_with_llm([], [], "test-model")
        self.assertEqual(result, [])
        mock_client.assert_not_called()


class BuildGroupsTests(unittest.TestCase):
    def test_transitive_merge(self):
        # 0-1同一、1-2同一 -> 0,1,2は同じグループ
        groups = theme_merge.build_groups(3, [(0, 1), (1, 2)], [True, True])
        self.assertEqual(sorted(sorted(g) for g in groups), [[0, 1, 2]])

    def test_independent_groups_stay_separate(self):
        groups = theme_merge.build_groups(4, [(0, 1), (2, 3)], [True, False])
        self.assertEqual(sorted(sorted(g) for g in groups), [[0, 1], [2], [3]])

    def test_no_pairs_keeps_everything_separate(self):
        groups = theme_merge.build_groups(3, [], [])
        self.assertEqual(sorted(sorted(g) for g in groups), [[0], [1], [2]])


class MergeGroupTests(unittest.TestCase):
    def test_single_article_group_returned_unchanged(self):
        articles = [_article(item_id="a", final_score=3.0)]
        merged = theme_merge.merge_group(articles, [0])
        self.assertEqual(merged["item_id"], "a")
        self.assertNotIn("merged_sources", merged)

    def test_representative_is_highest_final_score(self):
        articles = [
            _article(item_id="a", final_score=2.0, source="Hacker News (AI Agent)"),
            _article(item_id="b", final_score=4.5, source="Claude Code Releases"),
        ]
        merged = theme_merge.merge_group(articles, [0, 1])
        self.assertEqual(merged["item_id"], "b")

    def test_merged_sources_lists_all_distinct_sources(self):
        articles = [
            _article(item_id="a", source="Hacker News (AI Agent)"),
            _article(item_id="b", source="Claude Code Releases"),
        ]
        merged = theme_merge.merge_group(articles, [0, 1])
        self.assertEqual(merged["merged_sources"], ["Claude Code Releases", "Hacker News (AI Agent)"])

    def test_multi_source_bonus_is_added_and_capped(self):
        articles = [
            _article(item_id="a", final_score=3.0, source="S1"),
            _article(item_id="b", final_score=2.0, source="S2"),
            _article(item_id="c", final_score=1.0, source="S3"),
        ]
        merged = theme_merge.merge_group(articles, [0, 1, 2])
        self.assertAlmostEqual(merged["final_score"], 3.0 + min(0.3 * 2, 0.6))


class MergeCandidatesTests(unittest.TestCase):
    def test_fewer_than_two_candidates_skips_merge_entirely(self):
        articles = [_article(item_id="a")]
        with patch.object(theme_merge.genai, "Client") as mock_client:
            result = theme_merge.merge_candidates(articles, "test-model")
        self.assertEqual(result, articles)
        mock_client.assert_not_called()

    def test_end_to_end_merges_similar_pair(self):
        articles = [
            _article(item_id="a", title="Claude Code v2.1 released", source="Claude Code Releases", final_score=3.0),
            _article(item_id="b", title="Claude Code v2.1 is released today", source="Hacker News (AI Agent)", final_score=4.0),
        ]
        response = types.SimpleNamespace(text=json.dumps({"results": [{"index": 1, "same_topic": True}]}))
        client = types.SimpleNamespace(models=types.SimpleNamespace(generate_content=lambda **kwargs: response))
        with patch.object(theme_merge.genai, "Client", return_value=client), patch.dict("os.environ", {"GEMINI_API_KEY": "test"}):
            result = theme_merge.merge_candidates(articles, "test-model")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["item_id"], "b")
        self.assertIn("merged_sources", result[0])


if __name__ == "__main__":
    unittest.main()
