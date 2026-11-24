"""
Every query below is scoped to `properties.environment = 'production'`.
The PostHog project currently holding real traffic (265973, confusingly
named "Default project" - see the step 0 audit) mixes development, staging
and production events together; filtering by `environment` is how
production-only figures come out of it.
"""

from __future__ import annotations

import os

import requests

from date_utils import london_day_range_utc, london_week_start

POSTHOG_API_HOST = "https://eu.posthog.com"


def _run_hogql_query(query: str) -> list[list]:
    project_id = os.environ["POSTHOG_PROJECT_ID"]
    api_key = os.environ["POSTHOG_API_KEY"]
    response = requests.post(
        f"{POSTHOG_API_HOST}/api/projects/{project_id}/query/",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"query": {"kind": "HogQLQuery", "query": query}},
        timeout=30,
    )
    response.raise_for_status()
    return response.json().get("results", [])


def _to_hogql_timestamp(instant) -> str:
    return instant.strftime("%Y-%m-%d %H:%M:%S")


def _count_event(event_name: str, in_window: str) -> int:
    rows = _run_hogql_query(f"select count() from events where event = '{event_name}' and {in_window}")
    return rows[0][0] if rows else 0


def _count_users_on_path(path_prefix: str, in_window: str) -> int:
    rows = _run_hogql_query(
        f"select count(distinct person_id) from events where event = '$pageview' and properties.$pathname like '{path_prefix}%' and {in_window}"
    )
    return rows[0][0] if rows else 0


# App routes that correspond to the design's "feature coverage" breakdown
# (see src/components/App/App.tsx in oso-frontend). "Lina" has no route of
# its own - it is not a standalone page - so it cannot be measured this way
# and is left out, not guessed.
FEATURE_COVERAGE_PATHS = {
    "Calendar": "/calendar",
    "Contacts": "/clients",
    "Payments": "/payments",
    "Services": "/services",
    "Dashboard": "/dashboard",
}


def _average_session_seconds(in_window: str) -> float | None:
    """Mean session length: max(timestamp) - min(timestamp) per $session_id, averaged. Sessions with only one event (duration 0) are included, same as a real single-pageview visit."""
    rows = _run_hogql_query(
        f"""
        select avg(duration) from (
          select properties.$session_id as session_id, dateDiff('second', min(timestamp), max(timestamp)) as duration
          from events where {in_window} and properties.$session_id is not null
          group by session_id
        )
        """
    )
    return rows[0][0] if rows and rows[0][0] is not None else None


def _count_breakdown(select_expr: str, in_window: str) -> dict:
    """Generic `group by` breakdown: {value: count}, dropping a null grouping key rather than guessing a label for it. `is not None` (not truthiness) so a legitimate falsy value like hour 0 survives."""
    rows = _run_hogql_query(f"select {select_expr}, count() from events where {in_window} group by {select_expr}")
    return {label: count for label, count in rows if label is not None}


def _sessions_per_user_week_to_date(date_str: str) -> float | None:
    """Distinct sessions / distinct active users from this London week's Monday through the given day - a true week-to-date ratio, not a sum of daily figures (which would double-count a person active on multiple days)."""
    week_start_utc, _ = london_day_range_utc(london_week_start(date_str))
    _, week_end_utc_exclusive = london_day_range_utc(date_str)
    window = (
        f"properties.environment = 'production' "
        f"and timestamp >= '{_to_hogql_timestamp(week_start_utc)}' and timestamp < '{_to_hogql_timestamp(week_end_utc_exclusive)}'"
    )
    rows = _run_hogql_query(
        f"select count(distinct properties.$session_id), count(distinct person_id) from events where {window}"
    )
    if not rows:
        return None
    sessions, users = rows[0]
    return round(sessions / users, 1) if users else None


def fetch_posthog_daily_raw(date_str: str) -> dict:
    start_utc, end_utc_exclusive = london_day_range_utc(date_str)
    start = _to_hogql_timestamp(start_utc)
    end = _to_hogql_timestamp(end_utc_exclusive)
    in_window = f"properties.environment = 'production' and timestamp >= '{start}' and timestamp < '{end}'"

    trial_rows = _run_hogql_query(f"select count() from events where event = 'trial_started' and {in_window}")
    # signup_channel doesn't exist yet (step 0(b)) - this returns empty until it's added to trial_started.
    channel_rows = _run_hogql_query(
        f"select properties.signupChannel, count() from events where event = 'trial_started' and {in_window} group by properties.signupChannel"
    )
    # Autocapture is restricted to buttons and [data-ph-capture] elements - link-based CTAs
    # not yet tagged won't show up here. See the step 0 audit's CTA-click note.
    cta_rows = _run_hogql_query(f"select count() from events where event = '$autocapture' and {in_window}")
    active_user_rows = _run_hogql_query(f"select count(distinct person_id) from events where {in_window}")

    sign_ups_by_channel = {(channel or "unknown"): count for channel, count in channel_rows}

    feature_coverage_users = {
        feature: _count_users_on_path(path, in_window) for feature, path in FEATURE_COVERAGE_PATHS.items()
    }

    return {
        "new_trial_sign_ups": trial_rows[0][0] if trial_rows else 0,
        "sign_ups_by_channel": sign_ups_by_channel,
        "cta_clicks": cta_rows[0][0] if cta_rows else 0,
        "active_users": active_user_rows[0][0] if active_user_rows else 0,
        # Beta view - each of these is a straight count of an event that
        # already exists and fires live (confirmed in the step 0 audit),
        # no new app instrumentation needed.
        "tasks_ticked_done": _count_event("task_completed", in_window),
        "paid_ticks": _count_event("payment_marked_paid", in_window),
        "clients_added": _count_event("client_created", in_window),
        "lina_reminders_sent": _count_event("payment_reminder_sent", in_window),
        "tasks_created": _count_event("task_created", in_window),
        # Number of distinct users who visited each app section at least
        # once, keyed by feature name. Divide by active_users for a %.
        # "Lina" is deliberately absent - it has no route of its own.
        "feature_coverage_users": feature_coverage_users,
        "avg_session_seconds": _average_session_seconds(in_window),
        # Usage metrics - all three properties are captured automatically by
        # PostHog's own autocapture, no new instrumentation needed.
        "hour_of_day_counts": _count_breakdown("toHour(toTimeZone(timestamp, 'Europe/London'))", in_window),
        "device_type_counts": _count_breakdown("properties.$device_type", in_window),
        "os_counts": _count_breakdown("properties.$os", in_window),
        "sessions_per_active_user_week_to_date": _sessions_per_user_week_to_date(date_str),
    }
