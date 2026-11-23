"""
Day/week-to-date/month-to-date comparisons for one source on one date.

How a metric behaves over a period:
 - "sum": a flow - add up each day's value for a period total (revenue,
   sign-ups).
 - "last": a stock/point-in-time reading - summing across days would be
   meaningless (e.g. "total paying users" isn't additive), so week/month
   comparisons use the same point-in-time reading against the equivalent
   date in the prior period instead of a period sum.

Structured fields (breakdowns like `churn_reasons`) aren't listed in the
metric-kind maps below - they're carried in the raw snapshot for detail
views, not rolled up.
"""

from __future__ import annotations

from date_utils import (
    add_london_calendar_days,
    dates_between_inclusive,
    london_month_start,
    london_week_start,
    same_london_day_last_month,
)

STRIPE_METRIC_KINDS = {
    "revenue_pence": "sum",
    "new_paid_sign_ups": "sum",
    "total_paying_users": "last",
    "churned_subscriptions": "sum",
    "failed_payments": "sum",
    "payments_attempted": "sum",
    "payments_succeeded": "sum",
    "straight_through_payments": "sum",
    "recovered_payments": "sum",
}

POSTHOG_METRIC_KINDS = {
    "new_trial_sign_ups": "sum",
    "cta_clicks": "sum",
    "active_users": "last",
}

METRIC_KINDS_BY_SOURCE = {
    "stripe": STRIPE_METRIC_KINDS,
    "posthog": POSTHOG_METRIC_KINDS,
}


def compute_comparison(current: float | None, previous: float | None) -> dict:
    if current is None or previous is None:
        return {"value": current, "previous_value": previous, "change": None, "change_percent": None}
    change = current - previous
    change_percent = None if previous == 0 else (change / previous) * 100
    return {"value": current, "previous_value": previous, "change": change, "change_percent": change_percent}


def _point_value(raw_by_date: dict, date_str: str, key: str) -> float | None:
    raw = raw_by_date.get(date_str)
    if raw is None or key not in raw:
        return None
    return raw[key]


def _sum_range(raw_by_date: dict, dates: list[str], key: str) -> float | None:
    """Sums `key` across every date in the range; `None` if any day has no usable snapshot (a partial sum would understate the period silently)."""
    total = 0
    for date_str in dates:
        raw = raw_by_date.get(date_str)
        if raw is None or key not in raw:
            return None
        total += raw[key]
    return total


def _period_value(kind: str, raw_by_date: dict, dates: list[str], point_date: str, key: str) -> float | None:
    if kind == "sum":
        return _sum_range(raw_by_date, dates, key)
    return _point_value(raw_by_date, point_date, key)


def build_rollup(source: str, date_str: str, raw_by_date: dict) -> dict:
    """
    Builds the full rollup for one source on one date. `raw_by_date` must
    contain every date this needs - `rollup_input_date_range` tells callers
    exactly what range to load.
    """
    metric_kinds = METRIC_KINDS_BY_SOURCE[source]
    prior_day = add_london_calendar_days(date_str, -1)
    last_week_same_day = add_london_calendar_days(date_str, -7)

    week_start = london_week_start(date_str)
    week_dates = dates_between_inclusive(week_start, date_str)
    last_week_start = add_london_calendar_days(week_start, -7)
    last_week_dates = dates_between_inclusive(last_week_start, last_week_same_day)

    month_start = london_month_start(date_str)
    month_dates = dates_between_inclusive(month_start, date_str)
    last_month_same_day = same_london_day_last_month(date_str)
    last_month_start = london_month_start(last_month_same_day)
    last_month_dates = dates_between_inclusive(last_month_start, last_month_same_day)

    today: dict = {}
    week_to_date: dict = {}
    month_to_date: dict = {}

    for key, kind in metric_kinds.items():
        current_value = _point_value(raw_by_date, date_str, key)

        today[key] = {
            "vs_yesterday": compute_comparison(current_value, _point_value(raw_by_date, prior_day, key)),
            "vs_last_week": compute_comparison(current_value, _point_value(raw_by_date, last_week_same_day, key)),
        }

        week_to_date[key] = compute_comparison(
            _period_value(kind, raw_by_date, week_dates, date_str, key),
            _period_value(kind, raw_by_date, last_week_dates, last_week_same_day, key),
        )

        month_to_date[key] = compute_comparison(
            _period_value(kind, raw_by_date, month_dates, date_str, key),
            _period_value(kind, raw_by_date, last_month_dates, last_month_same_day, key),
        )

    return {"source": source, "date": date_str, "today": today, "week_to_date": week_to_date, "month_to_date": month_to_date}


def rollup_input_date_range(date_str: str) -> tuple[str, str]:
    """The full span of dates `build_rollup` might read for a given date - fetch snapshots for exactly this range."""
    month_start = london_month_start(date_str)
    last_month_same_day = same_london_day_last_month(date_str)
    last_month_start = london_month_start(last_month_same_day)
    week_start = london_week_start(date_str)
    last_week_start = add_london_calendar_days(week_start, -7)
    earliest = min(last_month_start, last_week_start, month_start)
    return earliest, date_str
