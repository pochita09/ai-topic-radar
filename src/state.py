import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

STATE_FILE = Path(__file__).parent.parent / "data" / "last_seen.json"


def _load() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        print("警告: last_seen.json の読み込みに失敗しました。初回実行として扱います。")
        return {}


def atomic_write_json(path: Path, data: object) -> None:
    """Write JSON through a temporary file so a crash cannot corrupt state."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # 一時ファイルに書いてからアトミックにリネーム（書き込み中のクラッシュでファイルが壊れない）
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _save(state: dict) -> None:
    atomic_write_json(STATE_FILE, state)


def get_last_seen(feed_url: str) -> datetime | None:
    ts = _load().get(feed_url)
    if ts is None:
        return None
    return datetime.fromisoformat(ts)


def update_many(updates: dict[str, datetime]) -> None:
    """複数フィードの last_seen を一括更新する（読み込み1回・書き込み1回）。"""
    if not updates:
        return
    state = _load()
    for feed_url, dt in updates.items():
        state[feed_url] = dt.isoformat()
    _save(state)


def update_last_seen(feed_url: str, dt: datetime) -> None:
    update_many({feed_url: dt})
