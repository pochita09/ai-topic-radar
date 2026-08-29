import sys
from datetime import datetime, timezone
from pathlib import Path

# src/ をパスに追加して output.mailer 等のサブパッケージを import できるようにする
sys.path.insert(0, str(Path(__file__).parent))

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

from ai_filter import filter_and_summarize
from fetcher import fetch_feed
from hn_fetcher import fetch_hn
from archive import load_articles, save_articles
from renderer import render_monitor
from runtime_config import apply_settings, fetch_settings
from state import get_last_seen, update_last_seen, update_many

MAX_ARTICLES_PER_CALL = 100  # 1回の実行でAIに渡す記事数の上限


def load_config() -> dict:
    with open(ROOT / "config.yaml", "r", encoding="utf-8") as f:
        defaults = yaml.safe_load(f)
    return apply_settings(defaults, fetch_settings(defaults.get("worker_url", "")))


def main() -> None:
    # 実行時刻はワークフローの cron が決める。起動したら必ず処理する。
    config = load_config()
    model_name = config["ai"]["model"]
    archive = load_articles()
    archived_ids = {article["item_id"] for article in archive}
    saved_articles: list[dict] = []
    fetched_count = 0
    pending_state: dict[str, datetime] = {}

    for theme in config["themes"]:
        print(f"\n[テーマ] {theme['name']}")
        all_new_articles = []

        for source in theme["sources"]:
            if not source.get("enabled", True):
                print(f"  [{source['name']}] 設定により無効化されています")
                continue
            last_seen = get_last_seen(source["url"])
            is_first_run = last_seen is None

            fetch = fetch_hn if source.get("type") == "hacker_news" else fetch_feed
            articles, newest_date = fetch(source, last_seen)

            if is_first_run:
                # 初回実行: ウォーターマークを即時保存（配信する記事がないため安全）
                # newest_date が None のフィード（日付なし）も now で初期化して無限スキップを防ぐ（fix #6）
                watermark = newest_date or datetime.now(timezone.utc)
                update_last_seen(source["url"], watermark)
                print(f"  [{source['name']}] 初回実行: 既存記事をスキップしました")
                continue

            fetched_count += len(articles)
            unseen_articles = [article for article in articles if article["item_id"] not in archived_ids]
            print(f"  [{source['name']}] 取得: {len(articles)}件 / Gemini対象の新着: {len(unseen_articles)}件")
            for a in unseen_articles:
                a["_feed_url"] = source["url"]  # ウォーターマーク計算用（内部フィールド）
            all_new_articles.extend(articles)

            if not unseen_articles and newest_date is not None:
                pending_state[source["url"]] = newest_date

        all_candidates = [article for article in all_new_articles if article["item_id"] not in archived_ids]
        if not all_candidates:
            print("  Gemini対象の新着記事なし")
            continue

        # 上限を超える場合は先頭 MAX_ARTICLES_PER_CALL 件に切り捨て
        candidates = all_candidates
        if len(candidates) > MAX_ARTICLES_PER_CALL:
            print(f"    警告: 記事数が上限を超えるため先頭 {MAX_ARTICLES_PER_CALL} 件に制限します（合計 {len(candidates)} 件）")
            candidates = candidates[:MAX_ARTICLES_PER_CALL]

        # 切り捨て後の記事からウォーターマークを計算（処理範囲と記録を一致させる）
        print(f"  Gemini採点中... ({len(candidates)}件 → {model_name})")
        try:
            scored = filter_and_summarize(candidates, theme, model_name)
        except Exception as e:
            print(f"  警告: Gemini処理失敗 [{theme['name']}]: {e} - このテーマを次回再試行します")
            continue
        if len(scored) != len(candidates):
            print(f"  警告: Gemini結果が不完全です ({len(scored)}/{len(candidates)})。未処理記事は次回再試行します")
        processed_at = datetime.now(timezone.utc).isoformat()
        for article in scored:
            article.pop("_feed_url", None)
            article["processed_at"] = processed_at
        saved_articles.extend(scored)
        archived_ids.update(article["item_id"] for article in scored)

        scored_ids = {article["item_id"] for article in scored}
        all_candidates_by_feed: dict[str, int] = {}
        selected_by_feed: dict[str, int] = {}
        for article in all_candidates:
            feed_url = article.get("_feed_url", "")
            all_candidates_by_feed[feed_url] = all_candidates_by_feed.get(feed_url, 0) + 1
        for article in candidates:
            feed_url = article.get("_feed_url", "")
            selected_by_feed[feed_url] = selected_by_feed.get(feed_url, 0) + 1

        # 上限で一部を残したフィードはウォーターマークを進めない。
        # 次回はアーカイブ済みIDを除外して残りだけをGeminiへ送る。
        if all(article["item_id"] in scored_ids for article in candidates):
            for article in candidates:
                feed_url = article.get("_feed_url", "")
                if feed_url and selected_by_feed.get(feed_url) == all_candidates_by_feed.get(feed_url):
                    published = datetime.fromisoformat(article["published_at"])
                    if feed_url not in pending_state or published > pending_state[feed_url]:
                        pending_state[feed_url] = published
        print(f"  Gemini成功: {len(scored)}件")

    try:
        all_articles = save_articles(archive, saved_articles) if saved_articles else archive
        output = render_monitor(all_articles, config, fetched_count, len(saved_articles))
        state_changes = {
            feed_url: timestamp
            for feed_url, timestamp in pending_state.items()
            if get_last_seen(feed_url) != timestamp
        }
        update_many(state_changes)
    except Exception as e:
        print(f"\n警告: アーカイブまたはHTML生成に失敗したため既読状態を更新しません: {e}")
        return
    print(f"  状態更新: {len(state_changes)}ソース")
    print(f"  HTML生成: {output}")
    print(f"\n完了: 保存 {len(saved_articles)}件 / HTML: {output}")


if __name__ == "__main__":
    main()
