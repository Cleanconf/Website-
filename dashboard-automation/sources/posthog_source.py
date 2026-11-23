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

from date_utils import london_day_range_utc

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

    return {
        "new_trial_sign_ups": trial_rows[0][0] if trial_rows else 0,
        "sign_ups_by_channel": sign_ups_by_channel,
        "cta_clicks": cta_rows[0][0] if cta_rows else 0,
        "active_users": active_user_rows[0][0] if active_user_rows else 0,
    }
