from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))


def jst_date(iso_timestamp: str) -> str:
    """UTC ISO タイムスタンプをJST日付（YYYY-MM-DD）に変換する。cronの実行時刻(JST基準)と揃える。"""
    return datetime.fromisoformat(iso_timestamp).astimezone(JST).date().isoformat()


def candidates_for_date(articles: list[dict], topic_id: str, verification_threshold: int, report_date: str) -> list[dict]:
    """
    report_date（JST日付, 'YYYY-MM-DD'）に処理された記事から、一次フィルタで
    捨てられたもの(decision=SKIP)と検証価値が足切りライン未満のものを除いた候補を返す
    （TOP5選抜・テーマ統合の前段。ソート・件数制限はしない）。
    """
    return [
        article for article in articles
        if article.get("topic_id") == topic_id
        and article.get("decision") != "SKIP"
        and article.get("verification_score", 0) >= verification_threshold
        and article.get("processed_at")
        and jst_date(article["processed_at"]) == report_date
    ]


def top5_of(candidates: list[dict]) -> list[dict]:
    """候補（統合済みでもよい）を final_score 降順で上位5件に絞る。"""
    ranked = sorted(candidates, key=lambda article: (article.get("final_score", 0), article.get("published_at", "")), reverse=True)
    return ranked[:5]


def select_top5(articles: list[dict], topic_id: str, verification_threshold: int, report_date: str) -> list[dict]:
    """candidates_for_date + top5_of のショートカット（テーマ統合を行わない場合に使う）。"""
    return top5_of(candidates_for_date(articles, topic_id, verification_threshold, report_date))
