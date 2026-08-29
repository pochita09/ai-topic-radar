import feedparser
import hashlib
import re
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


TRACKING_QUERY_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid"}


def _normalise_title(title: str) -> str:
    """Keep the identifier stable across harmless whitespace/case changes."""
    return re.sub(r"\s+", " ", title).strip().casefold()


def _normalise_url(url: str) -> str:
    """Remove fragments and common tracking parameters without changing article paths."""
    parts = urlsplit(url.strip())
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in TRACKING_QUERY_KEYS
    ]
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/") or "/", urlencode(sorted(query)), ""))


def make_item_id(url: str, title: str, published_at: datetime) -> str:
    """Stable article ID based on canonical URL, title and UTC publication timestamp."""
    material = "\n".join((_normalise_url(url), _normalise_title(title), published_at.astimezone(timezone.utc).isoformat()))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _parse_date(entry) -> datetime | None:
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t:
            return datetime(*t[:6], tzinfo=timezone.utc)
    return None


def fetch_feed(source: dict, last_seen: datetime | None) -> tuple[list[dict], datetime | None]:
    """
    RSSフィードを取得し、last_seen より新しい記事を返す。
    初回実行（last_seen=None）は空リストと最新記事日時を返す。

    Returns: (new_articles, newest_date)
    """
    feed = feedparser.parse(source["url"])

    if feed.bozo and not feed.entries:
        print(f"    警告: フィード取得失敗 [{source['name']}] {feed.bozo_exception}")
        return [], last_seen

    newest_date = last_seen
    articles = []

    for entry in feed.entries:
        published = _parse_date(entry)
        if published is None:
            continue

        if newest_date is None or published > newest_date:
            newest_date = published

        if last_seen is None or published <= last_seen:
            continue

        title = entry.get("title", "").strip()
        url = entry.get("link", "").strip()
        if not title or not url:
            print(f"    警告: 記事にタイトルまたはURLがありません [{source['name']}]")
            continue

        articles.append({
            "item_id": make_item_id(url, title, published),
            "title": title,
            "url": url,
            "summary": entry.get("summary", ""),
            "source": source["name"],
            "channel": source.get("channel", "RSS"),
            "published_at": published.isoformat(),
        })

    return articles, newest_date
