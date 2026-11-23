import json

from slack_post import build_failure_notice, build_slack_message


def _base_input(**overrides) -> dict:
    defaults = dict(
        date_str="2026-11-20",
        views=[
            {
                "view": "business_overview",
                "view_label": "Business overview",
                "headline_metrics": [
                    {
                        "label": "Revenue",
                        "source": "stripe",
                        "formatted_value": "£1,234",
                        "comparison": {"value": 1234, "previous_value": 1000, "change": 234, "change_percent": 23.4},
                        "status": "On target",
                    }
                ],
                "actions": [{"title": "Chase failed payments", "detail": "Three cards declined yesterday."}],
            }
        ],
        stale_sources=[],
        dashboard_url="https://app.osoorganised.co.uk/admin/dashboard",
        claude_calls_used=1,
        claude_daily_cap=10,
    )
    defaults.update(overrides)
    return defaults


def test_includes_the_date_in_the_header():
    message = build_slack_message(**_base_input())
    assert message["blocks"][0] == {"type": "header", "text": {"type": "plain_text", "text": "OSO dashboard — 2026-11-20"}}


def test_shows_arrow_percent_and_status_word_together():
    message = build_slack_message(**_base_input())
    text = next(b["text"]["text"] for b in message["blocks"] if "Revenue" in json.dumps(b))
    assert "▲" in text
    assert "+23.4%" in text
    assert "(On target)" in text


def test_flat_glyph_and_not_available_yet_with_nothing_to_compare():
    message = build_slack_message(
        **_base_input(
            views=[
                {
                    "view": "business_overview",
                    "view_label": "Business overview",
                    "headline_metrics": [
                        {
                            "label": "Revenue",
                            "source": "stripe",
                            "formatted_value": "£0",
                            "comparison": {"value": None, "previous_value": None, "change": None, "change_percent": None},
                            "status": "Watch",
                        }
                    ],
                    "actions": [],
                }
            ]
        )
    )
    blob = json.dumps(message["blocks"], ensure_ascii=False)
    assert "▬" in blob
    assert "not available yet" in blob


def test_lists_prioritised_actions_under_their_view():
    message = build_slack_message(**_base_input())
    blob = json.dumps(message["blocks"])
    assert "Chase failed payments" in blob
    assert "Three cards declined yesterday." in blob


def test_calls_out_stale_sources():
    message = build_slack_message(**_base_input(stale_sources=["posthog"]))
    blob = json.dumps(message["blocks"])
    assert "Stale" in blob
    assert "PostHog" in blob


def test_omits_stale_warning_when_nothing_is_stale():
    message = build_slack_message(**_base_input(stale_sources=[]))
    assert "Stale" not in json.dumps(message["blocks"])


def test_includes_dashboard_link_and_run_usage():
    message = build_slack_message(**_base_input())
    blob = json.dumps(message["blocks"])
    assert "app.osoorganised.co.uk/admin/dashboard" in blob
    assert "1/10 Claude calls today" in blob


def test_plain_text_fallback():
    message = build_slack_message(**_base_input())
    assert "2026-11-20" in message["text"]
    assert "Business overview" in message["text"]


def test_build_failure_notice():
    notice = build_failure_notice("2026-11-20", "Stripe timed out")
    assert "2026-11-20" in notice["text"]
    assert "Stripe timed out" in notice["text"]
    assert ":x:" in json.dumps(notice["blocks"])
