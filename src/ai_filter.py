import json
import os
import re

from google import genai

# Phase4: 一次フィルタの基準は指示書で固定されているため、テーマ設定では編集できない
# 固定ロジックとしてここに埋め込む。ユーザーが調整するのは紹介価値・検証価値の基準文のみ。
FIRST_STAGE_CRITERIA = """
【一次フィルタ：関連性判定】
残す（いずれかに該当）：
Claude Code / Codex / AIエージェント / AI開発 / AI自動化 / 新しいAIツール /
AIワークフロー / AIコーディング / 注目OSS / モデル比較 / コスト削減 /
作業効率化 / 非エンジニアでも再現可能なAI活用

原則捨てる（いずれかに該当）：
AI業界の人事 / 資金調達だけのニュース / 論文紹介だけ / 細かすぎるバグ修正 /
社会論・政治論 / 実際に試す方法がないもの / 検証しても結果がほぼ自明なもの
""".strip()

DECISIONS = ("GO", "HOLD", "SKIP")
COST_LEVELS = ("low", "medium", "high")


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def _build_prompt(articles: list[dict], intro_criteria: str, verification_criteria: str) -> str:
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

    return f"""あなたは「Xで紹介すべきニュース」ではなく「自分で検証すると価値のあるテーマ」を選ぶ
AI情報キュレーターです。記事を1件も省略せず判定してください。記事本文にない事実は補わないでください。

{FIRST_STAGE_CRITERIA}

一次フィルタで「捨てる」に該当する記事は intro_score / verification_score を 0 にし、
decision を "SKIP" にしてください。残った記事だけを以下の2軸で 0〜5 の整数で採点してください。

【紹介価値（0〜5）】
{intro_criteria}

【検証価値（0〜5）】
{verification_criteria}

日本語タイトルは、原題の単純な直訳ではなく、3〜5秒で内容を判断できる短い見出しにしてください。
要約は1〜2行の日本語、tags は内容を表す短い日本語または英字タグを最大5個にしてください。
decision は、紹介価値・検証価値がともに十分なら "GO"、判断が難しければ "HOLD"、
一次フィルタで捨てるべきなら "SKIP" にしてください。reason には判断根拠を1行で書いてください。

【記事リスト】
{articles_text}

【出力形式】
JSON のみを返してください（説明文不要）:
{{
  "results": [
    {{
      "index": 1,
      "title_ja": "内容を端的に示す日本語見出し",
      "summary_ja": "1〜2行の日本語要約",
      "tags": ["タグ"],
      "intro_score": 0,
      "verification_score": 0,
      "reader_question": "読者が次に知りたいこと",
      "test_idea": "推奨する検証方法",
      "metrics": ["測るべき数字"],
      "estimated_time": "推定所要時間",
      "estimated_cost_level": "low",
      "decision": "GO",
      "reason": "判断理由"
    }}
  ]
}}
"""


def filter_and_summarize(articles: list[dict], theme: dict, model_name: str) -> list[dict]:
    """Gemini API で紹介価値・検証価値の2軸採点を行う。不正な結果の単一記事は除外する。"""
    if not articles:
        return []

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    prompt = _build_prompt(
        articles,
        theme.get("intro_criteria", ""),
        theme.get("verification_criteria", ""),
    )
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

    intro_weight = float(theme.get("intro_weight", 0.4))
    verification_weight = float(theme.get("verification_weight", 0.6))

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

        intro_score = item.get("intro_score")
        verification_score = item.get("verification_score")
        summary_ja = item.get("summary_ja")
        title_ja = item.get("title_ja")
        tags = item.get("tags")

        if isinstance(intro_score, bool) or not isinstance(intro_score, int) or not 0 <= intro_score <= 5:
            print(f"    警告: AI応答の記事 intro_score が不正です: index={index}")
            continue
        if isinstance(verification_score, bool) or not isinstance(verification_score, int) or not 0 <= verification_score <= 5:
            print(f"    警告: AI応答の記事 verification_score が不正です: index={index}")
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

        decision = item.get("decision")
        if decision not in DECISIONS:
            print(f"    警告: AI応答の記事 decision が不正です: index={index} - HOLD として扱います")
            decision = "HOLD"

        metrics = item.get("metrics")
        if not isinstance(metrics, list) or not all(isinstance(m, str) for m in metrics):
            metrics = []

        estimated_cost_level = item.get("estimated_cost_level")
        if estimated_cost_level not in COST_LEVELS:
            estimated_cost_level = "medium"

        final_score = round(intro_score * intro_weight + verification_score * verification_weight, 2)

        original = articles[idx]
        scored.append({
            **original,
            "intro_score": intro_score,
            "verification_score": verification_score,
            "final_score": final_score,
            "summary_ja": summary_ja.strip(),
            "title_ja": title_ja.strip()[:120] if isinstance(title_ja, str) else "",
            "tags": [tag.strip()[:40] for tag in tags[:5]],
            "reader_question": (item.get("reader_question") or "").strip()[:300],
            "test_idea": (item.get("test_idea") or "").strip()[:300],
            "metrics": [m.strip()[:60] for m in metrics[:6]],
            "estimated_time": (item.get("estimated_time") or "").strip()[:60],
            "estimated_cost_level": estimated_cost_level,
            "decision": decision,
            "reason": (item.get("reason") or "").strip()[:300],
            "topic_id": theme["topic_id"],
        })
    return scored
