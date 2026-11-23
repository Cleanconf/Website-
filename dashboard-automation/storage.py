"""
JSON-file storage for the dashboard job - no database at all, matching this
repo's existing automation pattern (e.g. publish_schedule.json). Everything
lives under data/, one small JSON file per thing, committed to the repo by
the GitHub Actions workflow after a real (non-dry-run) run.
"""

from __future__ import annotations

import json
from pathlib import Path

from date_utils import add_london_calendar_days, london_month_label
from rollups import METRIC_KINDS_BY_SOURCE

DATA_ROOT = Path(__file__).parent / "data"
SNAPSHOTS_DIR = DATA_ROOT / "snapshots"
ROLLUPS_DIR = DATA_ROOT / "rollups"
SERIES_DIR = DATA_ROOT / "series"
INSIGHTS_DIR = DATA_ROOT / "insights"
RUNS_DIR = DATA_ROOT / "runs"
CONFIG_DIR = DATA_ROOT / "config"

STALE_LOOKBACK_DAYS = 14


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")


def _snapshot_path(source: str, date_str: str) -> Path:
    return SNAPSHOTS_DIR / source / f"{date_str}.json"


def get_snapshot(source: str, date_str: str) -> dict | None:
    return _read_json(_snapshot_path(source, date_str))


def has_successful_snapshot(source: str, date_str: str) -> bool:
    snapshot = get_snapshot(source, date_str)
    return bool(snapshot and snapshot.get("status") == "ok")


def write_snapshot_and_update_series(source: str, date_str: str, status: str, raw: dict | None, error: str | None) -> None:
    """Writes a snapshot and, if it succeeded, rolls its contribution into the 12-month series."""
    previous = get_snapshot(source, date_str)
    previous_raw = previous.get("raw") if previous and previous.get("status") == "ok" else None

    _write_json(_snapshot_path(source, date_str), {"source": source, "date": date_str, "status": status, "raw": raw, "error": error})

    if status == "ok" and raw:
        _update_series(source, date_str, raw, previous_raw)


def _update_series(source: str, date_str: str, new_raw: dict, previous_raw: dict | None) -> None:
    """Folds one day's contribution into the rolling 12-month series, trimming to the most recent 12 months. `previous_raw`, on a `force` re-run, lets this subtract the old contribution first so it never double-counts."""
    path = SERIES_DIR / f"{source}.json"
    series = _read_json(path) or {"source": source, "months": []}
    metric_kinds = METRIC_KINDS_BY_SOURCE[source]
    month = london_month_label(date_str)

    months_by_label = {m["month"]: m for m in series["months"]}
    entry = months_by_label.setdefault(month, {"month": month, "values": {}})

    for key, kind in metric_kinds.items():
        new_value = new_raw.get(key, 0)
        old_value = (previous_raw or {}).get(key, 0)
        if kind == "sum":
            entry["values"][key] = entry["values"].get(key, 0) + (new_value - old_value)
        else:
            entry["values"][key] = new_value  # "last": overwrite - ends up as the latest date processed in the month.

    months = sorted(months_by_label.values(), key=lambda m: m["month"])[-12:]
    _write_json(path, {"source": source, "months": months})


def get_raw_by_date_range(source: str, dates: list[str]) -> dict:
    """Reads snapshots for every date into the shape `rollups`/`rules` expect - `None` for a missing or errored day."""
    raw_by_date = {}
    for date_str in dates:
        snapshot = get_snapshot(source, date_str)
        raw_by_date[date_str] = snapshot["raw"] if snapshot and snapshot.get("status") == "ok" else None
    return raw_by_date


def get_latest_good_raw(source: str, date_str: str) -> tuple[str, dict] | None:
    """
    Walks backward from `date_str` (inclusive) looking for the most recent
    snapshot that succeeded - what Slack shows for a stale source ("showing
    the last good figures") rather than a blank. Bounded to 14 days.
    """
    cursor = date_str
    for _ in range(STALE_LOOKBACK_DAYS):
        snapshot = get_snapshot(source, cursor)
        if snapshot and snapshot.get("status") == "ok" and snapshot.get("raw"):
            return cursor, snapshot["raw"]
        cursor = add_london_calendar_days(cursor, -1)
    return None


def write_rollup(rollup: dict) -> None:
    _write_json(ROLLUPS_DIR / rollup["source"] / f"{rollup['date']}.json", rollup)


def write_insight(insight: dict) -> None:
    _write_json(INSIGHTS_DIR / f"{insight['view']}_{insight['date']}.json", insight)


def get_run(date_str: str) -> dict | None:
    return _read_json(RUNS_DIR / f"{date_str}.json")


def write_run(date_str: str, run: dict) -> None:
    _write_json(RUNS_DIR / f"{date_str}.json", run)


def get_targets_config() -> dict:
    from rules import DEFAULT_TARGETS_CONFIG

    config = _read_json(CONFIG_DIR / "targets.json")
    if not config:
        return DEFAULT_TARGETS_CONFIG
    merged_targets = {**DEFAULT_TARGETS_CONFIG["targets"], **config.get("targets", {})}
    return {"flag_threshold_fraction": config.get("flag_threshold_fraction", DEFAULT_TARGETS_CONFIG["flag_threshold_fraction"]), "targets": merged_targets}


def ensure_targets_config_exists() -> None:
    from rules import DEFAULT_TARGETS_CONFIG

    path = CONFIG_DIR / "targets.json"
    if not path.exists():
        _write_json(path, DEFAULT_TARGETS_CONFIG)


CLAUDE_DAILY_CALL_CAP = 10


def try_reserve_claude_call(date_str: str) -> bool:
    """Checks today's Claude call count against the daily cap and reserves one if under it."""
    path = CONFIG_DIR / "claude_usage.json"
    usage = _read_json(path) or {}
    used_today = usage.get(date_str, 0)
    if used_today >= CLAUDE_DAILY_CALL_CAP:
        return False
    usage[date_str] = used_today + 1
    _write_json(path, usage)
    return True
