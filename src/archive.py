import json
from pathlib import Path

from state import atomic_write_json


ARCHIVE_FILE = Path(__file__).parent.parent / "data" / "articles.json"


def load_articles() -> list[dict]:
    if not ARCHIVE_FILE.exists():
        return []
    try:
        with open(ARCHIVE_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
        if not isinstance(data, list):
            raise ValueError("記事アーカイブのルートは配列である必要があります")
        return [article for article in data if isinstance(article, dict) and article.get("item_id")]
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"警告: articles.json の読み込みに失敗しました。空のアーカイブとして扱います: {error}")
        return []


def save_articles(existing: list[dict], new_articles: list[dict]) -> list[dict]:
    """Upsert by item_id and retain a bounded, newest-first local archive."""
    by_id = {article["item_id"]: article for article in existing if article.get("item_id")}
    for article in new_articles:
        by_id[article["item_id"]] = article
    articles = sorted(by_id.values(), key=lambda article: article.get("processed_at", ""), reverse=True)[:1000]
    atomic_write_json(ARCHIVE_FILE, articles)
    return articles
