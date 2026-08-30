from pathlib import Path

ROOT = Path(__file__).parent.parent
REPORTS_DIR = ROOT / "reports"


def _render_section(theme_name: str, top5: list[dict]) -> str:
    lines = [f"## {theme_name}", ""]
    if not top5:
        lines.append("本日は選定条件を満たす記事がありませんでした。")
        lines.append("")
        return "\n".join(lines)

    for i, article in enumerate(top5, 1):
        title = article.get("title_ja") or article.get("title", "")
        metrics = article.get("metrics") or []
        lines.append(f"### {i}. {title}")
        lines.append(f"- 紹介価値: {article.get('intro_score', 0)}/5 ／ 検証価値: {article.get('verification_score', 0)}/5")
        lines.append(f"- 何が起きたか: {article.get('summary_ja', '')}")
        lines.append(f"- 読者が次に知りたいこと: {article.get('reader_question', '')}")
        lines.append(f"- 推奨する検証方法: {article.get('test_idea', '')}")
        lines.append(f"- 測るべき数字: {'、'.join(metrics) if metrics else 'なし'}")
        lines.append(f"- 推定所要時間: {article.get('estimated_time', '')} ／ 推定費用: {article.get('estimated_cost_level', '')}")
        merged_sources = article.get("merged_sources")
        if merged_sources:
            lines.append(f"- 情報源: {' / '.join(merged_sources)}")
        lines.append(f"- 一次情報URL: {article.get('url', '')}")
        lines.append("")
    return "\n".join(lines)


def render_report(sections: list[tuple[str, list[dict]]], report_date: str) -> str:
    """sections: [(テーマ名, top5), ...]。人間が3分で読み終わる分量の日次Markdownレポートを生成する。"""
    lines = [f"# 日次レポート — {report_date}", ""]
    for theme_name, top5 in sections:
        lines.append(_render_section(theme_name, top5))
    return "\n".join(lines)


def write_report(sections: list[tuple[str, list[dict]]], report_date: str) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    output = REPORTS_DIR / f"{report_date}.md"
    output.write_text(render_report(sections, report_date), encoding="utf-8")
    return output
