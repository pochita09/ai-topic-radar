"""Safely overlay the non-secret Monitor settings stored in Cloudflare KV."""

import copy
import json
import urllib.error
import urllib.request

USER_AGENT = "InformationMonitor/1.0 (+https://github.com/pochita09/information-monitor)"


def settings_payload(config: dict) -> dict:
    """Build the browser/Worker config shape from repository-owned defaults."""
    return {
        "topics": {
            theme["topic_id"]: {
                "display_name": theme.get("display_name", theme["name"]),
                "intro_criteria": theme.get("intro_criteria", ""),
                "verification_criteria": theme.get("verification_criteria", ""),
                "intro_weight": float(theme.get("intro_weight", 0.4)),
                "verification_weight": float(theme.get("verification_weight", 0.6)),
                "verification_threshold": int(theme.get("verification_threshold", 3)),
                "sources": {
                    source["source_id"]: {
                        "name": source["name"], "url": source["url"],
                        "enabled": bool(source.get("enabled", True)), "user_added": bool(source.get("user_added", False)),
                    }
                    for source in theme.get("sources", [])
                },
            }
            for theme in config.get("themes", [])
        },
        "run": {
            "keep_below_threshold": bool(config.get("run", {}).get("keep_below_threshold", True)),
            "read_dim_enabled": bool(config.get("run", {}).get("read_dim_enabled", True)),
        },
    }


def apply_settings(default_config: dict, settings: object) -> dict:
    """Apply only known, validated runtime values; malformed KV data changes nothing."""
    config = copy.deepcopy(default_config)
    if not isinstance(settings, dict):
        return config
    topics = settings.get("topics")
    if isinstance(topics, dict):
        for theme in config.get("themes", []):
            saved = topics.get(theme["topic_id"])
            if not isinstance(saved, dict):
                continue
            name = saved.get("display_name")
            intro_criteria = saved.get("intro_criteria")
            verification_criteria = saved.get("verification_criteria")
            intro_weight = saved.get("intro_weight")
            verification_weight = saved.get("verification_weight")
            verification_threshold = saved.get("verification_threshold")
            sources = saved.get("sources")
            if isinstance(name, str) and 0 < len(name.strip()) <= 80:
                theme["display_name"] = name.strip()
            if isinstance(intro_criteria, str) and 0 < len(intro_criteria.strip()) <= 4_000:
                theme["intro_criteria"] = intro_criteria.strip()
            if isinstance(verification_criteria, str) and 0 < len(verification_criteria.strip()) <= 4_000:
                theme["verification_criteria"] = verification_criteria.strip()
            if isinstance(intro_weight, (int, float)) and not isinstance(intro_weight, bool) and 0 <= intro_weight <= 1:
                theme["intro_weight"] = float(intro_weight)
            if isinstance(verification_weight, (int, float)) and not isinstance(verification_weight, bool) and 0 <= verification_weight <= 1:
                theme["verification_weight"] = float(verification_weight)
            if isinstance(verification_threshold, int) and not isinstance(verification_threshold, bool) and 0 <= verification_threshold <= 5:
                theme["verification_threshold"] = verification_threshold
            if isinstance(sources, dict):
                # config.yaml がソース一覧の正。KVは各ソースのON/OFFだけを預かる。
                # KVに無いソースはON、config.yamlに無いソースは無視する。
                for source in theme.get("sources", []):
                    saved_source = sources.get(source.get("source_id"))
                    if isinstance(saved_source, bool):
                        source["enabled"] = saved_source
                    elif isinstance(saved_source, dict) and isinstance(saved_source.get("enabled"), bool):
                        source["enabled"] = saved_source["enabled"]
    run = settings.get("run")
    if isinstance(run, dict):
        # 実行時刻はワークフローの cron が正。KVの times は取り込まない。
        for key in ("keep_below_threshold", "read_dim_enabled"):
            if isinstance(run.get(key), bool):
                config.setdefault("run", {})[key] = run[key]
    return config


def fetch_settings(url: str, timeout: float = 5.0) -> dict | None:
    """Read Worker config without a browser Origin. Fail closed to YAML defaults."""
    if not url:
        return None
    try:
        # Python-urllib のままだと Cloudflare のブラウザ判定（error 1010）で 403 になる。
        request = urllib.request.Request(
            url.rstrip("/") + "/config",
            headers={"Accept": "application/json", "User-Agent": USER_AGENT},
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return payload.get("config") if isinstance(payload, dict) else None
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as error:
        print(f"警告: 設定APIを取得できません。リポジトリ既定値を使用します: {error}")
        return None
