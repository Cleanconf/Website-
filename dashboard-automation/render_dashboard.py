"""
Builds dashboard-data.js from the stored snapshots/rollups/series - the only
thing dashboard.html reads. Never fabricates a number: anything not
genuinely measurable yet is written as null, which dashboard.html renders
as "Not available yet", never a guess or a silent zero.

Several simplifications versus the full design spec, worth knowing:
 - Per-section "status" is computed from the existing 7-day-average rule
   (rules.status_word) against each section's lead metric, since no real
   targets are set yet (every metric in DEFAULT_TARGETS_CONFIG is a
   placeholder) - not a bespoke per-section rule.
 - Per-section "reason" text is a short rule-based sentence from that
   status, not a generated narrative - the mockup's hand-written sentences
   ("3 of 9 cancellations gave no reason...") would need a dedicated
   Claude prompt per section, which is a reasonable next step but not
   built yet.
 - Insights come from the existing view-level Claude step (insights.py),
   mapped into the mockup's {priority, source, text} shape with a
   default "Medium" priority and no "Open: <source>" link, since that
   step does not ask Claude for a priority or a section id today - a
   small, separate prompt change would add those.
"""

from __future__ import annotations

import json
from pathlib import Path

from date_utils import add_london_calendar_days, dates_between_inclusive, same_london_day_last_month, yesterday_london
from rules import DEFAULT_TARGETS_CONFIG, seven_day_average, status_word
from storage import (
    get_dashboard_summary,
    get_raw_by_date_range,
    get_run,
)

DASHBOARD_HTML_DIR = Path(__file__).parent
TARGETS = DEFAULT_TARGETS_CONFIG


def _comparison_pair(rawByDate: dict, date_str: str, key: str):
    """Shorthand for a {v, d1, d7} Today-tile input, straight from stored daily raw values."""
    v = (rawByDate.get(date_str) or {}).get(key)
    d1 = (rawByDate.get(add_london_calendar_days(date_str, -1)) or {}).get(key)
    d7 = (rawByDate.get(add_london_calendar_days(date_str, -7)) or {}).get(key)
    return {"v": v, "d1": d1, "d7": d7}


def _week_month(rollup: dict, key: str) -> dict:
    wtd = rollup["week_to_date"].get(key, {})
    mtd = rollup["month_to_date"].get(key, {})
    return {
        "week": {"cur": wtd.get("value"), "prev": wtd.get("previous_value")},
        "month": {"cur": mtd.get("value"), "prev": mtd.get("previous_value")},
    }


def _empty_week_month() -> dict:
    return {"week": {"cur": None, "prev": None}, "month": {"cur": None, "prev": None}}


def _pct_breakdown(counts: dict | None) -> list[dict] | None:
    """Turns a {label: count} breakdown into a sorted [{label, value}] of percentage shares. `None` when there's nothing to show rather than a misleading empty chart."""
    if not counts:
        return None
    total = sum(counts.values())
    if not total:
        return None
    return sorted(
        ({"label": label, "value": round(count / total * 100, 1)} for label, count in counts.items()),
        key=lambda row: -row["value"],
    )


def _hour_label(hour) -> str:
    return f"{int(hour):02d}:00"


def _pence_to_pounds(week_month: dict) -> dict:
    def _convert(value):
        return value / 100 if value is not None else None

    return {period: {"cur": _convert(v["cur"]), "prev": _convert(v["prev"])} for period, v in week_month.items()}


_STATUS_WORD_TO_KEY = {"On target": "on", "Watch": "watch", "Off target": "off"}


def _section_status(raw_by_date: dict, date_str: str, key: str) -> str:
    """The mockup's status keys are lowercase on/watch/off (driving CSS classes and the glyph lookup) - rules.status_word() returns the human words, so translate between the two here."""
    current = (raw_by_date.get(date_str) or {}).get(key)
    average = seven_day_average(raw_by_date, date_str, key)
    target_cfg = TARGETS["targets"].get(key, {})
    word = status_word(current, average, target_cfg.get("target"), target_cfg.get("direction", "higher_is_better"), TARGETS["flag_threshold_fraction"])
    return _STATUS_WORD_TO_KEY[word]


_REASON_BY_STATUS = {
    "on": "On target - nothing needs attention here right now.",
    "watch": "Worth keeping an eye on - this has moved a bit off its usual level.",
    "off": "Off target - this has moved well off its usual level and may need a look.",
}


def _map_insights(insight_doc: dict | None) -> list[dict]:
    """Maps the stored {title, detail} actions into the mockup's {p, sec, src, t} shape. No priority or section link yet - see module docstring."""
    if not insight_doc:
        return []
    out = []
    for action in insight_doc.get("actions", []):
        out.append({"p": "Medium", "sec": None, "src": "PostHog", "t": f"{action['title']}. {action['detail']}"})
    return out


def _build_business(date_str: str) -> dict:
    stripe_range = get_raw_by_date_range("stripe", dates_between_inclusive_safe(date_str))
    posthog_range = get_raw_by_date_range("posthog", dates_between_inclusive_safe(date_str))
    meta_range = get_raw_by_date_range("meta", dates_between_inclusive_safe(date_str))

    stripe_rollup = _read_rollup("stripe", date_str)
    posthog_rollup = _read_rollup("posthog", date_str)
    meta_rollup = _read_rollup("meta", date_str)
    summary = get_dashboard_summary(date_str) or {}
    business_insight = next((v for v in summary.get("views", []) if v["view"] == "business_overview"), None)

    today_revenue = _comparison_pair(stripe_range, date_str, "revenue_pence")
    today_revenue = {k: (v / 100 if isinstance(v, (int, float)) else v) for k, v in today_revenue.items()}

    page_today = (meta_range.get(date_str) or {}).get("page_followers")
    page_y = (meta_range.get(add_london_calendar_days(date_str, -1)) or {}).get("page_followers")
    ig_today = (meta_range.get(date_str) or {}).get("ig_followers")
    ig_y = (meta_range.get(add_london_calendar_days(date_str, -1)) or {}).get("ig_followers")
    followers_gained_today = None
    if page_today is not None and page_y is not None and ig_today is not None and ig_y is not None:
        followers_gained_today = (page_today - page_y) + (ig_today - ig_y)

    churn_reasons_raw = (stripe_range.get(date_str) or {}).get("churn_reasons") or {}
    churn_reasons = [{"label": k.replace("_", " ").capitalize(), "value": v} for k, v in churn_reasons_raw.items()] or None

    today_posthog_for_usage = posthog_range.get(date_str) or {}
    hour_breakdown = _pct_breakdown(today_posthog_for_usage.get("hour_of_day_counts"))
    usage = {
        "hourOfDay": [{**row, "label": _hour_label(row["label"])} for row in hour_breakdown] if hour_breakdown else None,
        "device": _pct_breakdown(today_posthog_for_usage.get("device_type_counts")),
        "platform": _pct_breakdown(today_posthog_for_usage.get("os_counts")),
    }

    # Daily, not monthly: a 12-month chart needs 2 calendar months before it can draw
    # a line at all. Built from the same daily snapshots as everything else, this
    # shows a line from the second day of real data onward, and at OSO's current
    # size day-to-day movement is more informative than a monthly average anyway.
    trend_days = [(d, (stripe_range.get(d) or {}).get("total_paying_users")) for d in dates_between_inclusive_safe(date_str)]
    trend_days = [(d, v) for d, v in trend_days if v is not None]
    trend30d = None
    if len(trend_days) > 1:
        trend30d = {
            "labels": [d[8:10] for d, _ in trend_days],
            "values": [round(v) for _, v in trend_days],
        }

    meta_followers_rows = None
    if meta_rollup:
        fb = _week_month(meta_rollup, "page_followers")
        ig = _week_month(meta_rollup, "ig_followers")
        if fb["week"]["cur"] is not None or ig["week"]["cur"] is not None:
            meta_followers_rows = [
                {"channel": "Facebook", "total": fb["week"]["cur"], "week": fb["week"], "month": fb["month"]},
                {"channel": "Instagram", "total": ig["week"]["cur"], "week": ig["week"], "month": ig["month"]},
            ]

    now_paying = (stripe_range.get(date_str) or {}).get("total_paying_users")
    lw_paying = (stripe_range.get(add_london_calendar_days(date_str, -7)) or {}).get("total_paying_users")
    lm_paying = (stripe_range.get(same_london_day_last_month(date_str)) or {}).get("total_paying_users")

    return {
        "today": {
            "newTrial": _comparison_pair(posthog_range, date_str, "new_trial_sign_ups"),
            "newPaid": _comparison_pair(stripe_range, date_str, "new_paid_sign_ups"),
            "revenue": today_revenue,
            "failedPayments": _comparison_pair(stripe_range, date_str, "failed_payments"),
            "followersGained": {"v": followers_gained_today, "d1": None, "d7": None},
        },
        "insights": _map_insights(business_insight),
        "growth": _with_reason({
            "status": _section_status(stripe_range, date_str, "revenue_pence"),
            "revenue": _pence_to_pounds(_week_month(stripe_rollup, "revenue_pence")) if stripe_rollup else _empty_week_month(),
            "newTrial": _week_month(posthog_rollup, "new_trial_sign_ups") if posthog_rollup else _empty_week_month(),
            "newPaid": _week_month(stripe_rollup, "new_paid_sign_ups") if stripe_rollup else _empty_week_month(),
        }),
        "paying": _with_reason({
            "status": _section_status(stripe_range, date_str, "total_paying_users"),
            "now": now_paying,
            "vsLW": {"from": lw_paying, "to": now_paying},
            "vsLM": {"from": lm_paying, "to": now_paying},
            "trend30d": trend30d,
        }),
        "retention": _with_reason({
            "status": _section_status(stripe_range, date_str, "churned_subscriptions"),
            "churn": _week_month(stripe_rollup, "churned_subscriptions") if stripe_rollup else _empty_week_month(),
            "failedPayments": _week_month(stripe_rollup, "failed_payments") if stripe_rollup else _empty_week_month(),
            "churnReasons": churn_reasons,
        }),
        "marketing": _with_reason({
            "status": "watch" if meta_followers_rows is None else "on",
            "stale": None,
            "followers": meta_followers_rows,
            "usage": usage,
        }),
    }


def _build_beta(date_str: str) -> dict:
    stripe_range = get_raw_by_date_range("stripe", dates_between_inclusive_safe(date_str))
    posthog_range = get_raw_by_date_range("posthog", dates_between_inclusive_safe(date_str))
    summary = get_dashboard_summary(date_str) or {}
    beta_insight = next((v for v in summary.get("views", []) if v["view"] == "beta"), None)

    today_posthog = posthog_range.get(date_str) or {}
    today_stripe = stripe_range.get(date_str) or {}

    active_users = today_posthog.get("active_users")
    feature_coverage_users = today_posthog.get("feature_coverage_users") or {}
    feature_coverage = None
    if active_users:
        feature_coverage = [
            {"label": feature, "value": round(count / active_users * 100, 1)}
            for feature, count in feature_coverage_users.items()
        ]

    tasks_created = today_posthog.get("tasks_created")
    paid_ticks = today_posthog.get("paid_ticks")
    payment_recording_rate = round(paid_ticks / tasks_created * 100, 1) if tasks_created else None

    payments_attempted = today_stripe.get("payments_attempted")
    payments_succeeded = today_stripe.get("payments_succeeded")
    acceptance_rate = round(payments_succeeded / payments_attempted * 100, 1) if payments_attempted else None

    straight_through = today_stripe.get("straight_through_payments")
    recovered = today_stripe.get("recovered_payments")
    straight_through_total = (straight_through or 0) + (recovered or 0)
    straight_through_rate = round(straight_through / straight_through_total * 100, 1) if straight_through_total else None

    return {
        "today": {
            "activeUsers": _comparison_pair(posthog_range, date_str, "active_users"),
            "tasksTickedDone": _comparison_pair(posthog_range, date_str, "tasks_ticked_done"),
            "paidTicks": _comparison_pair(posthog_range, date_str, "paid_ticks"),
            "clientsAdded": _comparison_pair(posthog_range, date_str, "clients_added"),
            "linaRemindersSent": _comparison_pair(posthog_range, date_str, "lina_reminders_sent"),
        },
        "insights": _map_insights(beta_insight),
        "featureCoverage": feature_coverage,
        "avgSessionSeconds": today_posthog.get("avg_session_seconds"),
        "paymentRecordingRate": payment_recording_rate,
        "paymentRecordingCounts": {"paidTicks": paid_ticks, "tasksCreated": tasks_created},
        "linaRemindersSentYesterday": today_posthog.get("lina_reminders_sent"),
        "sessionsPerUserWeekToDate": today_posthog.get("sessions_per_active_user_week_to_date"),
        "technical": {
            "acceptanceRate": acceptance_rate,
            "straightThroughRate": straight_through_rate,
        },
    }


def _with_reason(section: dict) -> dict:
    section["reason"] = _REASON_BY_STATUS[section["status"]]
    return section


def _build_social(date_str: str) -> dict:
    meta_range = get_raw_by_date_range("meta", dates_between_inclusive_safe(date_str))
    run = get_run(date_str) or {}
    meta_stale = run.get("source_statuses", {}).get("meta") == "stale"

    page_gained = _comparison_pair(meta_range, date_str, "page_followers")
    ig_gained_raw = _comparison_pair(meta_range, date_str, "ig_followers")
    # "gained" is the day-over-day change of a point-in-time follower count, not the count itself.
    def _gained(pair):
        if pair["v"] is None or pair["d1"] is None:
            return {"v": None, "d1": None, "d7": None}
        return {"v": pair["v"] - pair["d1"], "d1": None, "d7": None}

    today_raw = meta_range.get(date_str) or {}
    ig_engagement_rate = today_raw.get("ig_engagement_rate")

    def _followers_block(key: str) -> dict:
        now = today_raw.get(key)
        y = (meta_range.get(add_london_calendar_days(date_str, -1)) or {}).get(key)
        lw = (meta_range.get(add_london_calendar_days(date_str, -7)) or {}).get(key)
        return {"now": now, "vsYesterday": {"from": y, "to": now}, "vsLastWeek": {"from": lw, "to": now}}

    ig_best_post = today_raw.get("ig_best_post")

    return {
        "today": {
            "igFollowersGained": _gained(ig_gained_raw),
            "igEngagementRate": {"v": (ig_engagement_rate * 100 if ig_engagement_rate is not None else None), "d1": None, "d7": None},
            "pageFollowersGained": _gained(page_gained),
        },
        "insights": [],
        "competitors": _read_competitors(),
        "facebook": {
            "status": "watch" if meta_stale else "watch",
            "reason": "Facebook best post, engagement rate and reach are not available with the current Meta permissions.",
            "followers": _followers_block("page_followers"),
            "bestPost": None,
            "engagementRate": None,
        },
        "instagram": {
            "status": "on" if ig_best_post else "watch",
            "reason": "Instagram reach is not available with the current Meta permissions." if ig_best_post else "No Instagram post yesterday.",
            "followers": _followers_block("ig_followers"),
            "bestPost": ig_best_post,
            "engagementRate": ig_engagement_rate,
        },
    }


def _read_competitors() -> dict:
    """Hand-maintained reference list (competitors.json) - not part of the daily pull, since Instagram's Business Discovery API is blocked pending Meta App Review (see social-research-brief-nov-dec-2026.md). Updated manually whenever new research is done."""
    path = DASHBOARD_HTML_DIR / "data" / "config" / "competitors.json"
    if not path.exists():
        return {"competitors": [], "influencers": [], "updated": None}
    with path.open() as f:
        data = json.load(f)
    return {"competitors": data.get("competitors", []), "influencers": data.get("influencers", []), "updated": data.get("updated")}


def _read_rollup(source: str, date_str: str) -> dict | None:
    path = DASHBOARD_HTML_DIR / "data" / "rollups" / source / f"{date_str}.json"
    if not path.exists():
        return None
    with path.open() as f:
        return json.load(f)


def dates_between_inclusive_safe(date_str: str) -> list[str]:
    """The 31-day lookback buildbusiness/social need (today, yesterday, last week, last month, 12mo trend already comes from series.json separately)."""
    return dates_between_inclusive(add_london_calendar_days(date_str, -31), date_str)


def build_dashboard_data(date_str: str) -> dict:
    run = get_run(date_str) or {}
    return {
        "meta": {
            "todayLabel": _format_weekday_date(add_london_calendar_days(date_str, 1)),
            "yesterdayLabel": _format_weekday_date(date_str),
            "runUsage": {"claudeCalls": run.get("claude_calls_used", 0)},
        },
        "business": _build_business(date_str),
        "social": _build_social(date_str),
        "beta": _build_beta(date_str),
    }


_WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _format_weekday_date(date_str: str) -> str:
    from datetime import date as _date

    y, m, d = (int(x) for x in date_str.split("-"))
    weekday = _WEEKDAYS[_date(y, m, d).weekday()]
    return f"{weekday} {d:02d}/{m:02d}/{y:04d}"


def write_dashboard_data(date_str: str | None = None) -> None:
    date_str = date_str or yesterday_london()
    data = build_dashboard_data(date_str)
    js = "window.DASHBOARD_DATA = " + json.dumps(data, indent=2) + ";\n"
    (DASHBOARD_HTML_DIR / "dashboard-data.js").write_text(js, encoding="utf-8")


if __name__ == "__main__":
    import sys

    write_dashboard_data(sys.argv[1] if len(sys.argv) > 1 else None)
    print(f"Wrote {DASHBOARD_HTML_DIR / 'dashboard-data.js'}")
