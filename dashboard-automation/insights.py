"""One Claude call per view, only when there's something flagged to react to and under the daily cap."""

from __future__ import annotations

import json
import os

import requests

from storage import try_reserve_claude_call

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-5"
MAX_TOKENS = 600


def _build_prompt(view: str, flagged_deltas: list[dict]) -> str:
    return "\n".join(
        [
            f'You are helping a non-technical founder of a UK cleaning-business app read her "{view}" dashboard.',
            "Below are the metrics that moved enough to be flagged today, each already compared against its 7-day average.",
            "Write exactly 3 prioritised actions, most important first. Plain English, no jargon, UK English, no em dashes.",
            'Reply with ONLY a JSON array of exactly 3 objects, each {"title": string, "detail": string}. No other text.',
            "",
            json.dumps(flagged_deltas, indent=2),
        ]
    )


def _parse_actions(text: str) -> list[dict]:
    parsed = json.loads(text)
    if not isinstance(parsed, list):
        raise ValueError("Expected a JSON array of actions")
    return [{"title": str(item["title"]), "detail": str(item["detail"])} for item in parsed]


def generate_insight(view: str, date_str: str, flagged_deltas: list[dict]) -> dict:
    if not flagged_deltas:
        return {"view": view, "date": date_str, "status": "skipped_no_flags", "flagged_deltas": flagged_deltas, "actions": []}

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {"view": view, "date": date_str, "status": "skipped_no_key", "flagged_deltas": flagged_deltas, "actions": []}

    if not try_reserve_claude_call(date_str):
        return {"view": view, "date": date_str, "status": "skipped_cap_reached", "flagged_deltas": flagged_deltas, "actions": []}

    try:
        response = requests.post(
            ANTHROPIC_API_URL,
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": MODEL, "max_tokens": MAX_TOKENS, "messages": [{"role": "user", "content": _build_prompt(view, flagged_deltas)}]},
            timeout=30,
        )
        response.raise_for_status()
        body = response.json()
        text = next((block["text"] for block in body["content"] if block["type"] == "text"), "[]")
        actions = _parse_actions(text)
        return {"view": view, "date": date_str, "status": "generated", "flagged_deltas": flagged_deltas, "actions": actions}
    except Exception as error:  # noqa: BLE001 - insights failing must never break the rest of the job
        print(f"[dashboard] Insight generation failed for {view}/{date_str}: {error}")
        return {"view": view, "date": date_str, "status": "error", "flagged_deltas": flagged_deltas, "actions": []}
