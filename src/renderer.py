import re
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from runtime_config import settings_payload


ROOT = Path(__file__).parent.parent
PUBLIC_DIR = ROOT / "public"
TEMPLATE_DIR = ROOT / "templates"
# Commit the approved v3 visual source with this repository so GitHub Actions
# can embed the same stylesheet as local generation.
MOCK_FILE = ROOT / "mock" / "information-monitor-ui-mock-v3.html"


def _mock_css() -> str:
    """Reuse the supplied mock's stylesheet verbatim so Phase 1 keeps its visual language."""
    try:
        text = MOCK_FILE.read_text(encoding="utf-8")
        match = re.search(r"<style>(.*?)</style>", text, flags=re.DOTALL)
        if match:
            return match.group(1)
    except OSError as error:
        print(f"警告: UIモックのCSSを読み込めません: {error}")
    raise RuntimeError("Monitor UI mock stylesheet is missing; refusing to publish unstyled HTML")


def _display_time(timestamp: str) -> str:
    try:
        return datetime.fromisoformat(timestamp).astimezone().strftime("%m-%d %H:%M")
    except (TypeError, ValueError):
        return timestamp


def render_monitor(articles: list[dict], config: dict, fetched_count: int, saved_count: int) -> Path:
    """Render the Phase 1 static Monitor page from the local article archive."""
    # Do not create a Pages-only diff merely because a no-op scheduled run occurred.
    archive_updated_at = max((article.get("processed_at", "") for article in articles), default="")
    topics = []
    for theme in config.get("themes", []):
        topic_id = theme["topic_id"]
        threshold = int(theme.get("threshold", 6))
        topic_articles = [article for article in articles if article.get("topic_id") == topic_id]
        topic_articles.sort(key=lambda article: (article.get("score", 0), article.get("published_at", "")), reverse=True)
        for article in topic_articles:
            article["published_label"] = _display_time(article.get("published_at", ""))
        topics.append({
            "topic_id": topic_id,
            "name": theme.get("display_name", theme["name"]),
            "criteria": theme.get("filter_prompt", ""),
            "threshold": threshold,
            "sources": theme.get("sources", []),
            "keep_below_threshold": bool(config.get("run", {}).get("keep_below_threshold", True)),
            "above": [article for article in topic_articles if article.get("score", 0) >= threshold],
            "below": [article for article in topic_articles if article.get("score", 0) < threshold],
        })

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template("monitor.html")
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    output = PUBLIC_DIR / "index.html"
    output.write_text(
        template.render(
            style_css=_mock_css(),
            topics=topics,
            generated_at=_display_time(archive_updated_at) if archive_updated_at else "記事はまだありません",
            archive_count=len(articles),
            worker_url=config.get("worker_url", ""),
            settings_config=settings_payload(config),
        ),
        encoding="utf-8",
    )
    return output
