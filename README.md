# AI Topic Radar

「Xで紹介すべきニュース」ではなく「自分で検証すると価値のあるテーマ」を毎朝最大5件だけ出すツール。

`pochita09/information-monitor` をベースに分離した個人用プロジェクト。RSS/Atomで収集した記事をGeminiで2軸（紹介価値・検証価値）採点し、`final_score = 紹介価値 × 0.4 + 検証価値 × 0.6` の上位5件のみを日次レポートとHTMLで出力する。

## 構成

- `src/` — 収集・採点・出力パイプライン（Python 3.12）
- `worker/` — Cloudflare Worker + KV（フィードバック保存・設定オーバーライド用、`information-monitor` とは別インスタンス）
- `.github/workflows/monitor.yml` — GitHub Actionsでの定期実行・GitHub Pages公開
- `config.yaml` — ソース・採点基準・Worker URL（差し替え箇所はここ1箇所）

## 状態

Phase 2（フォークと環境分離）完了。Phase 3（情報源の差し替え）以降は未着手。
