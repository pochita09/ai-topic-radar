from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))


def jst_date(iso_timestamp: str) -> str:
    """UTC ISO タイムスタンプをJST日付（YYYY-MM-DD）に変換する。cronの実行時刻(JST基準)と揃える。"""
    return datetime.fromisoformat(iso_timestamp).astimezone(JST).date().isoformat()


def select_top5(articles: list[dict], topic_id: str, verification_threshold: int, report_date: str) -> list[dict]:
    """
    report_date（JST日付, 'YYYY-MM-DD'）に処理された記事から、一次フィルタで
    捨てられたもの(decision=SKIP)と検証価値が足切りライン未満のものを除き、
    final_score降順で上位5件だけを返す。
    """
    candidates = [
        article for article in articles
        if article.get("topic_id") == topic_id
        and article.get("decision") != "SKIP"
        and article.get("verification_score", 0) >= verification_threshold
        and article.get("processed_at")
        and jst_date(article["processed_at"]) == report_date
    ]
    candidates.sort(key=lambda article: (article.get("final_score", 0), article.get("published_at", "")), reverse=True)
    return candidates[:5]
