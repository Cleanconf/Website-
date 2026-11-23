"""
Every status, arrow and target line carries a glyph AND a word (never
colour alone - one of the design principles the brief carries over from
the dashboard UI). "flat" marks "no prior data to compare against" rather
than implying a real zero change.
"""

from __future__ import annotations

import os

import requests

SOURCE_LABEL = {"stripe": "Stripe", "posthog": "PostHog", "meta": "Facebook/Instagram"}


def _arrow_for(comparison: dict) -> str:
    change = comparison["change"]
    if change is None:
        return "▬"  # flat glyph
    if change > 0:
        return "▲"  # up glyph
    if change < 0:
        return "▼"  # down glyph
    return "▬"


def _change_label(comparison: dict) -> str:
    change_percent = comparison["change_percent"]
    if change_percent is None:
        return "not available yet" if comparison["change"] is None else "vs n/a"
    sign = "+" if change_percent > 0 else ""
    return f"{sign}{change_percent:.1f}%"


def _headline_line(metric: dict) -> str:
    return f"*{metric['label']}*: {metric['formatted_value']} {_arrow_for(metric['comparison'])} {_change_label(metric['comparison'])} ({metric['status']})"


def _view_section(section: dict) -> list[dict]:
    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*{section['view_label']}*"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(_headline_line(m) for m in section["headline_metrics"])}},
    ]
    if section["actions"]:
        actions_text = "\n".join(f"{i + 1}. *{a['title']}* — {a['detail']}" for i, a in enumerate(section["actions"]))
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": actions_text}})
    if section.get("notes"):
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(section["notes"])}})
    return blocks


def build_slack_message(
    date_str: str,
    views: list[dict],
    stale_sources: list[str],
    dashboard_url: str,
    claude_calls_used: int,
    claude_daily_cap: int,
) -> dict:
    blocks: list[dict] = [{"type": "header", "text": {"type": "plain_text", "text": f"OSO dashboard — {date_str}"}}]

    for index, section in enumerate(views):
        if index > 0:
            blocks.append({"type": "divider"})
        blocks.extend(_view_section(section))

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
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"<{dashboard_url}|Open the dashboard> · Run usage: {claude_calls_used}/{claude_daily_cap} Claude calls today",
                }
            ],
        }
    )

    text = f"OSO dashboard — {date_str}\n" + "\n".join(
        f"{v['view_label']}: " + "; ".join(_headline_line(m) for m in v["headline_metrics"]) for v in views
    )

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
