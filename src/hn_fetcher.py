import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from fetcher import make_item_id

HN_SEARCH_URL = "https://hn.algolia.com/api/v1/search_by_date"
HITS_PER_PAGE = 50


def fetch_hn(source: dict, last_seen: datetime | None) -> tuple[list[dict], datetime | None]:
    """
    Hacker News (Algolia Search API) からキーワード検索で新着を取得する。
    fetch_feed と同じ契約: (new_articles, newest_date) を返す。
    source["url"] はウォーターマーク用の疑似URL（例: hn-search://ai-agent）。
    """
    query = source.get("query", "")
    min_points = int(source.get("min_points", 0))
    params = urllib.parse.urlencode({"tags": "story", "query": query, "hitsPerPage": HITS_PER_PAGE})
    request = urllib.request.Request(f"{HN_SEARCH_URL}?{params}", headers={"User-Agent": "Mozilla/5.0"})

    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            data = json.loads(response.read())
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as error:
        print(f"    警告: Hacker News取得失敗 [{source['name']}] {error}")
        return [], last_seen

    newest_date = last_seen
    articles = []

    for hit in data.get("hits", []):
        created_at_i = hit.get("created_at_i")
        if created_at_i is None:
            continue
        published = datetime.fromtimestamp(created_at_i, tz=timezone.utc)

        if newest_date is None or published > newest_date:
            newest_date = published

        if last_seen is None or published <= last_seen:
            continue

        points = hit.get("points") or 0
        if points < min_points:
            continue

        title = (hit.get("title") or "").strip()
        story_id = hit.get("story_id") or hit.get("objectID")
        discussion_url = f"https://news.ycombinator.com/item?id={story_id}"
        url = (hit.get("url") or discussion_url).strip()
        if not title or not url:
            continue

        articles.append({
            "item_id": make_item_id(url, title, published),
            "title": title,
            "url": url,
            "summary": f"Hacker News discussion: {discussion_url} (points={points}, comments={hit.get('num_comments') or 0})",
            "source": source["name"],
            "channel": source.get("channel", "Hacker News"),
            "published_at": published.isoformat(),
        })

    return articles, newest_date
