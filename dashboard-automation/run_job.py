#!/usr/bin/env python3
"""
Orchestrates one run of the dashboard job: fetches Stripe/PostHog/GA4 for a
London date, stores the snapshot and rollups, flags anomalies, asks Claude
for 3 actions (skipped gracefully with no key or nothing flagged), and
posts the Slack summary.

Usage:
    python3 run_job.py                        # yesterday (London), normal run
    python3 run_job.py --date 2026-11-15       # a specific / backfill date
    python3 run_job.py --from 2026-11-01 --to 2026-11-15   # backfill a range
    python3 run_job.py --force                 # re-fetch even if already done
    python3 run_job.py --dry-run               # build and log the Slack message, do not send it
"""

from __future__ import annotations

import argparse
import sys
import time
import traceback

from date_utils import dates_between_inclusive, yesterday_london
from formatting import format_count, format_pence
from insights import generate_insight
from rollups import METRIC_KINDS_BY_SOURCE, build_rollup, rollup_input_date_range
from rules import flag_all_metrics, seven_day_average, status_word
from slack_post import build_failure_notice, build_slack_message, post_to_slack
from sources.ga4_source import fetch_ga4_daily_raw
from sources.posthog_source import fetch_posthog_daily_raw
from sources.stripe_source import fetch_stripe_daily_raw
from storage import (
    ensure_targets_config_exists,
    get_latest_good_raw,
    get_raw_by_date_range,
    get_run,
    get_targets_config,
    has_successful_snapshot,
    write_insight,
    write_rollup,
    write_run,
    write_snapshot_and_update_series,
)

DASHBOARD_SOURCES = ["stripe", "posthog", "ga4"]
FETCHERS = {"stripe": fetch_stripe_daily_raw, "posthog": fetch_posthog_daily_raw, "ga4": fetch_ga4_daily_raw}
SOURCE_RETRIES = 2  # up to 2 retries (3 attempts total) with backoff.
SOURCE_TIMEOUT_SECONDS = 30

# A reasonable first cut at Business overview's 3-4 headline numbers,
# spanning all three sources. Will likely change once the full dashboard
# design (not just the design principles) is available.
BUSINESS_OVERVIEW_HEADLINES = [
    {"key": "revenue_pence", "label": "Revenue", "source": "stripe", "formatter": format_pence},
    {"key": "new_paid_sign_ups", "label": "New paid sign-ups", "source": "stripe", "formatter": format_count},
    {"key": "new_trial_sign_ups", "label": "New trial sign-ups", "source": "posthog", "formatter": format_count},
    {"key": "visitors", "label": "Website visitors", "source": "ga4", "formatter": format_count},
]


def _with_retries(fn, retries: int, base_delay_seconds: float = 1.0):
    last_error = None
    for attempt in range(retries + 1):
        try:
            return fn()
        except Exception as error:  # noqa: BLE001 - genuinely want to retry anything here
            last_error = error
            if attempt < retries:
                time.sleep(base_delay_seconds * (2**attempt))
    raise last_error


def fetch_source_snapshot(source: str, date_str: str, force: bool) -> str:
    if not force and has_successful_snapshot(source, date_str):
        return "ok"
    try:
        raw = _with_retries(lambda: FETCHERS[source](date_str), SOURCE_RETRIES)
        write_snapshot_and_update_series(source, date_str, "ok", raw, None)
        return "ok"
    except Exception as error:  # noqa: BLE001 - one source failing must not block the rest
        print(f"[dashboard] {source} snapshot failed for {date_str}: {error}", file=sys.stderr)
        traceback.print_exc()
        write_snapshot_and_update_series(source, date_str, "error", None, str(error))
        return "stale"


def build_headline_metric(spec: dict, date_str: str, source_status: str, raw_by_date: dict, rollups: dict, targets_config: dict) -> dict:
    if source_status == "ok":
        comparison = rollups[spec["source"]]["today"][spec["key"]]["vs_yesterday"]
        average = seven_day_average(raw_by_date[spec["source"]], date_str, spec["key"])
        target_cfg = targets_config["targets"].get(spec["key"], {})
        status = status_word(
            comparison["value"], average, target_cfg.get("target"), target_cfg.get("direction", "higher_is_better"), targets_config["flag_threshold_fraction"]
        )
        return {
            "label": spec["label"],
            "source": spec["source"],
            "formatted_value": "Not available yet" if comparison["value"] is None else spec["formatter"](comparison["value"]),
            "comparison": comparison,
            "status": status,
        }

    # Stale: fall back to the last good reading rather than showing a blank.
    fallback = get_latest_good_raw(spec["source"], date_str)
    value = fallback[1].get(spec["key"]) if fallback else None
    return {
        "label": spec["label"],
        "source": spec["source"],
        "formatted_value": "Not available yet" if value is None else spec["formatter"](value),
        "comparison": {"value": value, "previous_value": None, "change": None, "change_percent": None},
        "status": "Watch",
    }


def run_dashboard_job(date_str: str | None = None, force: bool = False, dry_run: bool = False) -> dict:
    date_str = date_str or yesterday_london()
    ensure_targets_config_exists()

    source_statuses = {}
    for source in DASHBOARD_SOURCES:
        source_statuses[source] = fetch_source_snapshot(source, date_str, force)

    from_date, to_date = rollup_input_date_range(date_str)
    date_range = dates_between_inclusive(from_date, to_date)

    raw_by_date = {}
    rollups = {}
    for source in DASHBOARD_SOURCES:
        raw_by_date[source] = get_raw_by_date_range(source, date_range)
        rollup = build_rollup(source, date_str, raw_by_date[source])
        rollups[source] = rollup
        write_rollup(rollup)

    targets_config = get_targets_config()

    flagged_deltas = []
    for source in DASHBOARD_SOURCES:
        flagged_deltas.extend(flag_all_metrics(source, date_str, raw_by_date[source], METRIC_KINDS_BY_SOURCE[source], targets_config))

    insight = generate_insight("business_overview", date_str, flagged_deltas)
    write_insight(insight)

    headline_metrics = [build_headline_metric(spec, date_str, source_statuses[spec["source"]], raw_by_date, rollups, targets_config) for spec in BUSINESS_OVERVIEW_HEADLINES]

    business_overview = {"view": "business_overview", "view_label": "Business overview", "headline_metrics": headline_metrics, "actions": insight["actions"]}
    stale_sources = [s for s in DASHBOARD_SOURCES if source_statuses[s] == "stale"]

    message = build_slack_message(
        date_str=date_str,
        views=[business_overview],
        stale_sources=stale_sources,
        dashboard_url="https://app.osoorganised.co.uk/admin/dashboard",
        claude_calls_used=1 if insight["status"] == "generated" else 0,
        claude_daily_cap=10,
    )

    posted = False
    if dry_run:
        print(f"[dashboard] Dry run — Slack message not sent:\n{message['text']}")
    else:
        existing_run = get_run(date_str)
        already_posted = bool(existing_run and existing_run.get("slack_posted"))
        if not already_posted or force:
            post_to_slack(message)
            posted = True

    write_run(
        date_str,
        {
            "date": date_str,
            "dry_run": dry_run,
            "force": force,
            "source_statuses": source_statuses,
            "slack_posted": posted,
            "claude_calls_used": 1 if insight["status"] == "generated" else 0,
        },
    )

    return {"date": date_str, "dry_run": dry_run, "source_statuses": source_statuses, "message": message, "posted": posted}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--date", help="A single London date (YYYY-MM-DD) to run for. Defaults to yesterday.")
    parser.add_argument("--from", dest="from_date", help="Start of a backfill date range (inclusive).")
    parser.add_argument("--to", dest="to_date", help="End of a backfill date range (inclusive).")
    parser.add_argument("--force", action="store_true", help="Re-fetch and overwrite even if a successful snapshot already exists.")
    parser.add_argument("--dry-run", action="store_true", help="Build everything and log the Slack message without sending it.")
    args = parser.parse_args()

    if args.from_date and args.to_date:
        dates = dates_between_inclusive(args.from_date, args.to_date)
    else:
        dates = [args.date] if args.date else [None]

    for date_str in dates:
        try:
            result = run_dashboard_job(date_str, force=args.force, dry_run=args.dry_run)
            print(f"[dashboard] Done for {result['date']}: posted={result['posted']} statuses={result['source_statuses']}")
        except Exception as error:  # noqa: BLE001 - a catastrophic failure still needs a Slack notice
            effective_date = date_str or yesterday_london()
            print(f"[dashboard] Job failed for {effective_date}: {error}", file=sys.stderr)
            traceback.print_exc()
            if not args.dry_run:
                try:
                    post_to_slack(build_failure_notice(effective_date, str(error)))
                except Exception as slack_error:  # noqa: BLE001
                    print(f"[dashboard] Failed to post failure notice to Slack: {slack_error}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
