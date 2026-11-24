"""
The actual figures live only on the dashboard HTML page (see README) and
in dashboard-automation/data/ - never duplicated into the Slack message
itself. Slack is just the daily nudge: a link, a stale-source warning if
one is needed, and the run usage line.
"""

from __future__ import annotations

import os

import requests

SOURCE_LABEL = {"stripe": "Stripe", "posthog": "PostHog", "meta": "Facebook/Instagram"}


def build_slack_message(
    date_str: str,
    stale_sources: list[str],
    claude_calls_used: int,
    claude_daily_cap: int,
    dashboard_url: str | None = None,
) -> dict:
    blocks: list[dict] = [{"type": "header", "text": {"type": "plain_text", "text": f"OSO dashboard — {date_str}"}}]

    # No dashboard page exists yet (a standalone HTML page, never part of
    # the web app - see README) - only show a link once dashboard_url is
    # actually set to something real, never a placeholder that 404s.
    link_text = f"<{dashboard_url}|Open today's dashboard>" if dashboard_url else "Dashboard page not published yet"
    blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": link_text}})

    if stale_sources:
        blocks.append({"type": "divider"})
        stale_labels = ", ".join(SOURCE_LABEL[s] for s in stale_sources)
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f":warning: Stale: {stale_labels} did not update today — showing the last good figures."},
            }
        )

    blocks.append({"type": "divider"})
    blocks.append(
        {"type": "context", "elements": [{"type": "mrkdwn", "text": f"Run usage: {claude_calls_used}/{claude_daily_cap} Claude calls today"}]}
    )

    text = f"OSO dashboard — {date_str}: " + (f"{dashboard_url}" if dashboard_url else "dashboard page not published yet")

    return {"blocks": blocks, "text": text}


def build_failure_notice(date_str: str, error: str) -> dict:
    text = f"OSO dashboard — {date_str}: the daily job failed ({error}). Nothing was posted for today."
    return {"text": text, "blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": f":x: {text}"}}]}


def post_to_slack(message: dict) -> None:
    """
    Posts via the Slack Bot Token (chat.postMessage) to the configured
    channel, reusing the same "OSO Content Review" app already used by the
    content automation (it already has chat:write) rather than setting up a
    separate incoming webhook - just needs inviting to the dashboard
    channel. Dry runs never call this - see run_job.py, which logs the
    built message instead.
    """
    response = requests.post(
        "https://slack.com/api/chat.postMessage",
        headers={"Authorization": f"Bearer {os.environ['SLACK_BOT_TOKEN']}"},
        json={"channel": os.environ["SLACK_CHANNEL_ID"], **message},
        timeout=30,
    )
    response.raise_for_status()
    body = response.json()
    if not body.get("ok"):
        raise RuntimeError(f"Slack API error: {body.get('error')}")
