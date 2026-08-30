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


def render_monitor(articles: list[dict], config: dict, fetched_count: int, saved_count: int, top5_by_topic: dict[str, list[dict]]) -> Path:
    """Render the static Monitor page from the local article archive."""
    # Do not create a Pages-only diff merely because a no-op scheduled run occurred.
    archive_updated_at = max((article.get("processed_at", "") for article in articles), default="")
    topics = []
    for theme in config.get("themes", []):
        topic_id = theme["topic_id"]
        verification_threshold = int(theme.get("verification_threshold", 3))
        topic_articles = [article for article in articles if article.get("topic_id") == topic_id]
        topic_articles.sort(key=lambda article: (article.get("final_score", 0), article.get("published_at", "")), reverse=True)
        for article in topic_articles:
            article["published_label"] = _display_time(article.get("published_at", ""))
        # Phase5/6: 表に出すのは本日(JST)・テーマ統合後のTOP5だけ（main.pyで算出済み）。
        # それ以外は全部「below」にまとめて折りたたむ（閾値未満・本日のTOP5に入らなかったもの両方）。
        top5 = top5_by_topic.get(topic_id, [])
        top5_ids = {article["item_id"] for article in top5}
        topics.append({
            "topic_id": topic_id,
            "name": theme.get("display_name", theme["name"]),
            "intro_criteria": theme.get("intro_criteria", ""),
            "verification_criteria": theme.get("verification_criteria", ""),
            "intro_weight": float(theme.get("intro_weight", 0.4)),
            "verification_weight": float(theme.get("verification_weight", 0.6)),
            "verification_threshold": verification_threshold,
            "sources": theme.get("sources", []),
            "keep_below_threshold": bool(config.get("run", {}).get("keep_below_threshold", True)),
            "above": top5,
            "below": [article for article in topic_articles if article["item_id"] not in top5_ids],
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
