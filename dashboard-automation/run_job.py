#!/usr/bin/env python3
"""
Orchestrates one run of the dashboard job: fetches Stripe/PostHog/Meta for
a London date, stores the snapshot and rollups, flags anomalies, asks
Claude for 3 actions per view (skipped gracefully with no key or nothing
flagged), writes a per-view summary for the (future) static HTML
dashboard page, and posts a short Slack message linking to it.

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
from render_dashboard import write_dashboard_data
from rollups import METRIC_KINDS_BY_SOURCE, build_rollup, rollup_input_date_range
from rules import flag_all_metrics, seven_day_average, status_word
from slack_post import build_failure_notice, build_slack_message, post_to_slack
from sources.meta_source import fetch_meta_daily_raw
from sources.posthog_source import fetch_posthog_daily_raw
from sources.stripe_source import fetch_stripe_daily_raw
from storage import (
    ensure_targets_config_exists,
    get_latest_good_raw,
    get_raw_by_date_range,
    get_run,
    get_targets_config,
    has_successful_snapshot,
    write_dashboard_summary,
    write_insight,
    write_rollup,
    write_run,
    write_snapshot_and_update_series,
)

FETCHERS = {"stripe": fetch_stripe_daily_raw, "posthog": fetch_posthog_daily_raw, "meta": fetch_meta_daily_raw}
SOURCE_RETRIES = 2  # up to 2 retries (3 attempts total) with backoff.
SOURCE_TIMEOUT_SECONDS = 30

# A reasonable first cut at Business overview's headline numbers, spanning
# both sources. Will likely change once the full dashboard design (not just
# the design principles) is available. No website-traffic headline for now -
# GA4 was removed, and PostHog isn't tracking the website yet (see README).
BUSINESS_OVERVIEW_HEADLINES = [
    {"key": "revenue_pence", "label": "Revenue", "source": "stripe", "formatter": format_pence},
    {"key": "new_paid_sign_ups", "label": "New paid sign-ups", "source": "stripe", "formatter": format_count},
    {"key": "new_trial_sign_ups", "label": "New trial sign-ups", "source": "posthog", "formatter": format_count},
]

# Facebook/Instagram followers only for now - reach and Facebook's own
# best-post/engagement need permissions this token doesn't have yet (see
# sources/meta_source.py). "Followers gained" isn't a separate headline:
# it's the same comparison engine's day-over-day change on these.
SOCIAL_MEDIA_HEADLINES = [
    {"key": "page_followers", "label": "Facebook followers", "source": "meta", "formatter": format_count},
    {"key": "ig_followers", "label": "Instagram followers", "source": "meta", "formatter": format_count},
]

# Each view's own sources (for Claude insights, which is one call per view)
# and which of DASHBOARD_SOURCES that spans.
VIEWS = [
    {"id": "business_overview", "label": "Business overview", "sources": ["stripe", "posthog"], "headlines": BUSINESS_OVERVIEW_HEADLINES},
    {"id": "social_media", "label": "Social media", "sources": ["meta"], "headlines": SOCIAL_MEDIA_HEADLINES},
]
DASHBOARD_SOURCES = sorted({source for view in VIEWS for source in view["sources"]})


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


def build_social_media_notes(date_str: str, source_status: str, raw_by_date: dict) -> list[str]:
    """Free-text lines for the social media view - the best Instagram post of the day, and a plain statement of what is not available yet rather than leaving it silently missing."""
    if source_status != "ok":
        return []
    raw = raw_by_date["meta"].get(date_str) or {}
    notes = []
    if raw.get("ig_best_post"):
        post = raw["ig_best_post"]
        rate = raw.get("ig_engagement_rate")
        rate_text = f"{rate * 100:.1f}% engagement" if rate is not None else "engagement rate not available"
        likes_text = "1 like" if post["likes"] == 1 else f"{post['likes']} likes"
        comments_text = "1 comment" if post["comments"] == 1 else f"{post['comments']} comments"
        notes.append(f"Best Instagram post: {likes_text}, {comments_text} ({rate_text}) — {post['permalink']}")
    else:
        notes.append("No Instagram post yesterday.")
    reasons = raw.get("not_available_reasons", {})
    if reasons:
        notes.append("Not available yet: Facebook best post, Facebook reach, Instagram reach — " + "; ".join(sorted(set(reasons.values()))))
    return notes


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

    view_sections = []
    claude_calls_used = 0
    for view in VIEWS:
        flagged_deltas = []
        for source in view["sources"]:
            flagged_deltas.extend(flag_all_metrics(source, date_str, raw_by_date[source], METRIC_KINDS_BY_SOURCE[source], targets_config))

        insight = generate_insight(view["id"], date_str, flagged_deltas)
        write_insight(insight)
        if insight["status"] == "generated":
            claude_calls_used += 1

        headline_metrics = [
            build_headline_metric(spec, date_str, source_statuses[spec["source"]], raw_by_date, rollups, targets_config) for spec in view["headlines"]
        ]
        notes = build_social_media_notes(date_str, source_statuses.get("meta"), raw_by_date) if view["id"] == "social_media" else []

        view_sections.append({"view": view["id"], "view_label": view["label"], "headline_metrics": headline_metrics, "actions": insight["actions"], "notes": notes})

    # Persisted for the (future) static HTML dashboard page to read - never
    # shown directly in Slack, which only gets a link to it (see slack_post.py).
    write_dashboard_summary(date_str, {"date": date_str, "views": view_sections})
    write_dashboard_data(date_str)  # dashboard-data.js, read by dashboard.html

    stale_sources = [s for s in DASHBOARD_SOURCES if source_statuses[s] == "stale"]

    # Published alongside the usual data commit (see the workflow's "Publish
    # to GitHub Pages" step) - unlisted (noindex, not linked from the public
    # site) but not access-controlled yet. Temporary, until a login gate is
    # in place.
    message = build_slack_message(
        date_str=date_str,
        stale_sources=stale_sources,
        claude_calls_used=claude_calls_used,
        claude_daily_cap=10,
        dashboard_url="https://osoorganised.co.uk/internal-dashboard/",
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
            "claude_calls_used": claude_calls_used,
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
