import json
import os
import re

from google import genai

def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def _build_prompt(articles: list[dict], filter_criteria: str) -> str:
    lines = []
    for i, a in enumerate(articles, 1):
        summary = _strip_html(a.get("summary", ""))[:300]
        lines.append(
            f"[{i}]\n"
            f"タイトル: {a['title']}\n"
            f"item_id: {a['item_id']}\n"
            f"URL: {a['url']}\n"
            f"概要: {summary}"
        )
    articles_text = "\n\n".join(lines)

    return f"""{filter_criteria}

あなたは記事を1件も省略せず、すべて1〜10の整数で採点する情報キュレーターです。
10 は基準に非常によく合い、1 はほとんど合いません。記事本文にない事実は補わないでください。
日本語タイトルは、原題の単純な直訳ではなく、3〜5秒で内容を判断できる短い見出しにしてください。
要約は1〜2行の日本語、tags は内容を表す短い日本語または英字タグを最大5個にしてください。

【記事リスト】
{articles_text}

【出力形式】
JSON のみを返してください（説明文不要）:
{{
  "results": [
    {{"index": 1, "score": 8, "title_ja": "内容を端的に示す日本語見出し", "category": "新モデル|新機能|価格改定|研究・論文|その他", "importance": "高|中|低", "summary_ja": "1〜2行の日本語要約", "tags": ["タグ"]}}
  ]
}}
"""


def filter_and_summarize(articles: list[dict], theme: dict, model_name: str) -> list[dict]:
    """Gemini API で全記事を1〜10点採点して返す。不正な結果の単一記事は除外する。"""
    if not articles:
        return []

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    prompt = _build_prompt(articles, theme["filter_prompt"])
    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config={"response_mime_type": "application/json"},
    )

    try:
        data = json.loads(response.text)
    except json.JSONDecodeError as e:
        print(f"    警告: AI応答のJSONパース失敗: {e}")
        return []

    scored = []
    for item in data.get("results", []):
        if not isinstance(item, dict):
            print("    警告: AI応答にオブジェクトではない結果が含まれています")
            continue
        index = item.get("index")
        if not isinstance(index, int):
            print("    警告: AI応答の記事 index が不正です")
            continue
        idx = index - 1
        if not (0 <= idx < len(articles)):
            print(f"    警告: AI応答の記事 index が範囲外です: {index}")
            continue
        score = item.get("score")
        summary_ja = item.get("summary_ja")
        title_ja = item.get("title_ja")
        tags = item.get("tags")
        if isinstance(score, bool) or not isinstance(score, int) or not 1 <= score <= 10:
            print(f"    警告: AI応答の記事 score が不正です: index={index}")
            continue
        if not isinstance(summary_ja, str) or not summary_ja.strip():
            print(f"    警告: AI応答の記事 summary_ja が不正です: index={index}")
            continue
        if title_ja is not None and (not isinstance(title_ja, str) or not title_ja.strip()):
            print(f"    警告: AI応答の記事 title_ja が不正です: index={index} - 原題を表示します")
            title_ja = None
        if not isinstance(tags, list) or not all(isinstance(tag, str) and tag.strip() for tag in tags):
            print(f"    警告: AI応答の記事 tags が不正です: index={index}")
            continue
        original = articles[idx]
        scored.append({
            **original,
            "category": item.get("category", "その他"),
            "importance": item.get("importance", "中"),
            "score": score,
            "summary_ja": summary_ja.strip(),
            "title_ja": title_ja.strip()[:120] if isinstance(title_ja, str) else "",
            "tags": [tag.strip()[:40] for tag in tags[:5]],
            "topic_id": theme["topic_id"],
        })
    return scored
