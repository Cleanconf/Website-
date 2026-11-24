from unittest.mock import patch

from sources.posthog_source import (
    _average_session_seconds,
    _count_event,
    _count_users_on_path,
    fetch_posthog_daily_raw,
)


def test_count_event_extracts_count_from_first_row():
    with patch("sources.posthog_source._run_hogql_query", return_value=[[5]]) as mocked:
        result = _count_event("task_completed", "1 = 1")
    assert result == 5
    assert "task_completed" in mocked.call_args[0][0]


def test_count_event_returns_zero_when_no_rows():
    with patch("sources.posthog_source._run_hogql_query", return_value=[]):
        assert _count_event("task_completed", "1 = 1") == 0


def test_count_users_on_path_extracts_count_and_uses_pathname_filter():
    with patch("sources.posthog_source._run_hogql_query", return_value=[[3]]) as mocked:
        result = _count_users_on_path("/calendar", "1 = 1")
    assert result == 3
    query = mocked.call_args[0][0]
    assert "$pathname" in query
    assert "/calendar" in query


def test_average_session_seconds_returns_value():
    with patch("sources.posthog_source._run_hogql_query", return_value=[[245.6]]):
        assert _average_session_seconds("1 = 1") == 245.6


def test_average_session_seconds_none_when_no_sessions_in_window():
    # avg() over zero grouped rows comes back as a row holding None, not an empty result set.
    with patch("sources.posthog_source._run_hogql_query", return_value=[[None]]):
        assert _average_session_seconds("1 = 1") is None


def _fake_query(query: str) -> list[list]:
    if "signupChannel" in query:
        return [["organic", 3], ["referral", 2]]
    if "trial_started" in query:
        return [[5]]
    if "$autocapture" in query:
        return [[12]]
    if "$pathname" in query:
        for feature, path in {
            "/calendar": 3,
            "/clients": 2,
            "/payments": 1,
            "/services": 1,
            "/dashboard": 0,
        }.items():
            if feature in query:
                return [[path]]
        raise AssertionError(f"unexpected path query: {query}")
    if "avg(duration)" in query:
        return [[245.6]]
    if "task_completed" in query:
        return [[0]]
    if "payment_marked_paid" in query:
        return [[7]]
    if "client_created" in query:
        return [[4]]
    if "payment_reminder_sent" in query:
        return [[2]]
    if "task_created" in query:
        return [[9]]
    if "count(distinct person_id) from events where" in query:
        return [[6]]
    raise AssertionError(f"unexpected query: {query}")


def test_fetch_posthog_daily_raw_shape():
    with patch("sources.posthog_source._run_hogql_query", side_effect=_fake_query):
        raw = fetch_posthog_daily_raw("2026-11-23")

    assert raw["new_trial_sign_ups"] == 5
    assert raw["sign_ups_by_channel"] == {"organic": 3, "referral": 2}
    assert raw["cta_clicks"] == 12
    assert raw["active_users"] == 6
    assert raw["tasks_ticked_done"] == 0
    assert raw["paid_ticks"] == 7
    assert raw["clients_added"] == 4
    assert raw["lina_reminders_sent"] == 2
    assert raw["tasks_created"] == 9
    assert raw["feature_coverage_users"] == {
        "Calendar": 3,
        "Contacts": 2,
        "Payments": 1,
        "Services": 1,
        "Dashboard": 0,
    }
    assert raw["avg_session_seconds"] == 245.6
