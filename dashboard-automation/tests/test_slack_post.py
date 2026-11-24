import json

from slack_post import build_failure_notice, build_slack_message


def _base_input(**overrides) -> dict:
    defaults = dict(
        date_str="2026-11-20",
        stale_sources=[],
        claude_calls_used=1,
        claude_daily_cap=10,
        dashboard_url="https://example.com/dashboard.html",
    )
    defaults.update(overrides)
    return defaults


def test_includes_the_date_in_the_header():
    message = build_slack_message(**_base_input())
    assert message["blocks"][0] == {"type": "header", "text": {"type": "plain_text", "text": "OSO dashboard — 2026-11-20"}}


def test_links_to_the_dashboard_page_when_a_url_is_given():
    message = build_slack_message(**_base_input())
    blob = json.dumps(message["blocks"])
    assert "example.com/dashboard.html" in blob
    assert "Open today's dashboard" in blob


def test_says_not_published_yet_without_a_url():
    message = build_slack_message(**_base_input(dashboard_url=None))
    blob = json.dumps(message["blocks"])
    assert "not published yet" in blob
    assert "example.com" not in blob


def test_never_includes_any_metric_data_only_a_link():
    """The actual figures live on the dashboard page and in data/ - never duplicated into the Slack message itself."""
    message = build_slack_message(**_base_input())
    blob = json.dumps(message["blocks"])
    assert "Revenue" not in blob
    assert "£" not in blob


def test_calls_out_stale_sources():
    message = build_slack_message(**_base_input(stale_sources=["posthog"]))
    blob = json.dumps(message["blocks"])
    assert "Stale" in blob
    assert "PostHog" in blob


def test_omits_stale_warning_when_nothing_is_stale():
    message = build_slack_message(**_base_input(stale_sources=[]))
    assert "Stale" not in json.dumps(message["blocks"])


def test_includes_run_usage():
    message = build_slack_message(**_base_input())
    assert "1/10 Claude calls today" in json.dumps(message["blocks"])


def test_plain_text_fallback():
    message = build_slack_message(**_base_input())
    assert "2026-11-20" in message["text"]


def test_build_failure_notice():
    notice = build_failure_notice("2026-11-20", "Stripe timed out")
    assert "2026-11-20" in notice["text"]
    assert "Stripe timed out" in notice["text"]
    assert ":x:" in json.dumps(notice["blocks"])
