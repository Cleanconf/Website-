"""
Dates are passed to GA4 as plain `YYYY-MM-DD` strings, not UTC instants -
the Data API buckets a report's days using the GA4 property's own
configured reporting timezone, not UTC. This only lines up with the
brief's Europe/London days if that property is configured with an
Europe/London (or UK) reporting timezone - check this in GA4 Admin ->
Property Settings; if it's left on the default (America/Los_Angeles),
every day here would be off by several hours.

Authenticates with a service account JSON key (GA4_SERVICE_ACCOUNT_JSON env
var, the whole key file as a single-line JSON string) rather than a Firebase
Functions runtime identity, since this now runs outside any Firebase
project. That service account needs Viewer access added in GA4 Admin ->
Property Access Management.
"""

from __future__ import annotations

import json
import os

import requests
from google.auth.transport.requests import Request
from google.oauth2 import service_account

GA4_DATA_API = "https://analyticsdata.googleapis.com/v1beta"
SCOPES = ["https://www.googleapis.com/auth/analytics.readonly"]

_credentials: service_account.Credentials | None = None


def _get_access_token() -> str:
    global _credentials
    if _credentials is None:
        info = json.loads(os.environ["GA4_SERVICE_ACCOUNT_JSON"])
        _credentials = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    if not _credentials.valid:
        _credentials.refresh(Request())
    return _credentials.token


def _run_report(body: dict) -> dict:
    property_id = os.environ["GA4_PROPERTY_ID"]
    response = requests.post(
        f"{GA4_DATA_API}/properties/{property_id}:runReport",
        headers={"Authorization": f"Bearer {_get_access_token()}"},
        json=body,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def metric_at(response: dict, index: int) -> float:
    rows = response.get("rows") or []
    if not rows:
        return 0
    value = rows[0]["metricValues"][index]["value"]
    return float(value) if value else 0


def dimension_breakdown(response: dict) -> dict:
    return {row["dimensionValues"][0]["value"]: float(row["metricValues"][0]["value"]) for row in response.get("rows") or []}


def page_list(response: dict) -> list[dict]:
    return [{"path": row["dimensionValues"][0]["value"], "sessions": float(row["metricValues"][0]["value"])} for row in response.get("rows") or []]


def fetch_ga4_daily_raw(date_str: str) -> dict:
    date_ranges = [{"startDate": date_str, "endDate": date_str}]

    totals = _run_report({"dateRanges": date_ranges, "metrics": [{"name": "totalUsers"}, {"name": "newUsers"}, {"name": "userEngagementDuration"}]})
    channels = _run_report({"dateRanges": date_ranges, "dimensions": [{"name": "sessionDefaultChannelGroup"}], "metrics": [{"name": "sessions"}]})
    top_pages = _run_report(
        {
            "dateRanges": date_ranges,
            "dimensions": [{"name": "pagePath"}],
            "metrics": [{"name": "sessions"}],
            "orderBys": [{"metric": {"metricName": "sessions"}, "desc": True}],
            "limit": "10",
        }
    )
    least_visited_pages = _run_report(
        {
            "dateRanges": date_ranges,
            "dimensions": [{"name": "pagePath"}],
            "metrics": [{"name": "sessions"}],
            "orderBys": [{"metric": {"metricName": "sessions"}, "desc": False}],
            "limit": "10",
        }
    )

    return {
        "visitors": metric_at(totals, 0),
        "new_visitors": metric_at(totals, 1),
        "top_pages": page_list(top_pages),
        "least_visited_pages": page_list(least_visited_pages),
        "total_dwell_seconds": metric_at(totals, 2),
        "sessions_by_channel": dimension_breakdown(channels),
    }
