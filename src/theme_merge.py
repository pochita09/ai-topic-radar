import difflib
import json
import os
import re
from datetime import datetime

from google import genai

TITLE_SIMILARITY_THRESHOLD = 0.5
DAYS_WINDOW = 3
MULTI_SOURCE_BONUS_PER_EXTRA_SOURCE = 0.3
MULTI_SOURCE_BONUS_CAP = 0.6


def _normalize_title(title: str) -> str:
    return re.sub(r"[^\w\s]", "", (title or "").lower()).strip()


def find_candidate_pairs(
    articles: list[dict],
    title_similarity_threshold: float = TITLE_SIMILARITY_THRESHOLD,
    days_window: int = DAYS_WINDOW,
) -> list[tuple[int, int]]:
    """
    LLMに投げる前の軽量な絞り込み。タイトル類似度と公開日時の近さだけで判定する
    （ローカル計算のためn²でもコストはほぼゼロ。LLM呼び出しをn²にしないための前段）。
    """
    pairs = []
    for i in range(len(articles)):
        for j in range(i + 1, len(articles)):
            a, b = articles[i], articles[j]
            try:
                date_a = datetime.fromisoformat(a.get("published_at", ""))
                date_b = datetime.fromisoformat(b.get("published_at", ""))
                if abs((date_a - date_b).days) > days_window:
                    continue
            except (ValueError, TypeError):
                pass
            title_a = _normalize_title(a.get("title_ja") or a.get("title", ""))
            title_b = _normalize_title(b.get("title_ja") or b.get("title", ""))
            similarity = difflib.SequenceMatcher(None, title_a, title_b).ratio()
            if similarity >= title_similarity_threshold:
                pairs.append((i, j))
    return pairs


def judge_pairs_with_llm(articles: list[dict], pairs: list[tuple[int, int]], model_name: str) -> list[bool]:
    """絞り込んだペアだけをGeminiに1回のバッチ呼び出しで「同じ話題か」判定させる。"""
    if not pairs:
        return []

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    lines = []
    for index, (i, j) in enumerate(pairs, 1):
        title_a = articles[i].get("title_ja") or articles[i].get("title", "")
        title_b = articles[j].get("title_ja") or articles[j].get("title", "")
        lines.append(f"[{index}]\nA: {title_a}\nB: {title_b}")

    prompt = f"""以下のペアが同じニュース・出来事について書かれているか判定してください。
別の媒体が同じ発表・リリース・議論を報じているだけなら「同じ」と判定してください。
関連はあるが別の出来事（別バージョン、別の話題など）なら「違う」と判定してください。

{chr(10).join(lines)}

JSON のみを返してください（説明文不要）:
{{"results": [{{"index": 1, "same_topic": true}}]}}
"""
    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config={"response_mime_type": "application/json"},
    )
    try:
        data = json.loads(response.text)
    except json.JSONDecodeError:
        return [False] * len(pairs)

    result_by_index = {}
    for item in data.get("results", []):
        if isinstance(item, dict) and isinstance(item.get("index"), int):
            result_by_index[item["index"]] = bool(item.get("same_topic"))
    return [result_by_index.get(position + 1, False) for position in range(len(pairs))]


def build_groups(count: int, pairs: list[tuple[int, int]], same_topic: list[bool]) -> list[list[int]]:
    """Union-Findで「同じ話題」と判定されたペアを推移的にグループ化する。"""
    parent = list(range(count))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        root_x, root_y = find(x), find(y)
        if root_x != root_y:
            parent[root_y] = root_x

    for (i, j), same in zip(pairs, same_topic):
        if same:
            union(i, j)

    groups: dict[int, list[int]] = {}
    for index in range(count):
        groups.setdefault(find(index), []).append(index)
    return list(groups.values())


def merge_group(articles: list[dict], group: list[int]) -> dict:
    """代表1件（final_score最高）にまとめ、情報源を併記し、複数ソースなら小さいボーナスを加算する。"""
    group_articles = [articles[i] for i in group]
    if len(group_articles) == 1:
        return group_articles[0]

    representative = max(group_articles, key=lambda article: article.get("final_score", 0))
    sources = sorted({article.get("source", "") for article in group_articles if article.get("source")})
    bonus = min(MULTI_SOURCE_BONUS_PER_EXTRA_SOURCE * (len(sources) - 1), MULTI_SOURCE_BONUS_CAP)

    merged = dict(representative)
    merged["merged_sources"] = sources
    merged["final_score"] = round(representative.get("final_score", 0) + bonus, 2)
    return merged


def merge_candidates(candidates: list[dict], model_name: str) -> list[dict]:
    """TOP5選抜前の候補記事に対してテーマ統合を行う。統合されなかった記事はそのまま含む。"""
    if len(candidates) < 2:
        return candidates
    pairs = find_candidate_pairs(candidates)
    if not pairs:
        return candidates
    same_topic = judge_pairs_with_llm(candidates, pairs, model_name)
    groups = build_groups(len(candidates), pairs, same_topic)
    return [merge_group(candidates, group) for group in groups]
