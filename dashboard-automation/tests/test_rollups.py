from date_utils import add_london_calendar_days
from rollups import build_rollup, compute_comparison

DATE = "2026-11-20"  # a Friday; its week starts Monday 2026-11-16.


def test_compute_comparison_basic():
    assert compute_comparison(120, 100) == {"value": 120, "previous_value": 100, "change": 20, "change_percent": 20}


def test_compute_comparison_null_safe():
    assert compute_comparison(None, 100) == {"value": None, "previous_value": 100, "change": None, "change_percent": None}
    assert compute_comparison(100, None) == {"value": 100, "previous_value": None, "change": None, "change_percent": None}


def test_compute_comparison_no_divide_by_zero():
    assert compute_comparison(5, 0) == {"value": 5, "previous_value": 0, "change": 5, "change_percent": None}


def _build_raw_by_date() -> dict:
    raw_by_date = {}
    current = "2026-10-01"
    while current <= DATE:
        raw_by_date[current] = {"new_trial_sign_ups": 1, "active_users": 999}
        current = add_london_calendar_days(current, 1)
    raw_by_date["2026-11-20"]["active_users"] = 500  # the date itself
    raw_by_date["2026-11-19"]["active_users"] = 480  # the day before
    raw_by_date["2026-11-13"]["active_users"] = 450  # same weekday last week
    raw_by_date["2026-10-20"]["active_users"] = 400  # same day last month
    return raw_by_date


def test_sums_a_flow_metric_over_week_and_month_to_date():
    rollup = build_rollup("posthog", DATE, _build_raw_by_date())
    # Mon 16 - Fri 20 = 5 days, both this week and last week (symmetric).
    assert rollup["week_to_date"]["new_trial_sign_ups"] == {"value": 5, "previous_value": 5, "change": 0, "change_percent": 0}
    # 1-20 November = 20 days; 1-20 October = 20 days (no clamping needed).
    assert rollup["month_to_date"]["new_trial_sign_ups"] == {"value": 20, "previous_value": 20, "change": 0, "change_percent": 0}


def test_compares_a_flow_metrics_today_figure():
    rollup = build_rollup("posthog", DATE, _build_raw_by_date())
    assert rollup["today"]["new_trial_sign_ups"]["vs_yesterday"] == {"value": 1, "previous_value": 1, "change": 0, "change_percent": 0}
    assert rollup["today"]["new_trial_sign_ups"]["vs_last_week"] == {"value": 1, "previous_value": 1, "change": 0, "change_percent": 0}


def test_does_not_sum_a_stock_metric():
    rollup = build_rollup("posthog", DATE, _build_raw_by_date())
    assert rollup["today"]["active_users"]["vs_yesterday"] == {
        "value": 500,
        "previous_value": 480,
        "change": 20,
        "change_percent": 20 / 480 * 100,
    }
    assert rollup["today"]["active_users"]["vs_last_week"] == {
        "value": 500,
        "previous_value": 450,
        "change": 50,
        "change_percent": 50 / 450 * 100,
    }
    # Week-to-date for a stock metric is "today vs the same weekday last week" again, not a sum.
    assert rollup["week_to_date"]["active_users"] == {
        "value": 500,
        "previous_value": 450,
        "change": 50,
        "change_percent": 50 / 450 * 100,
    }
    # Month-to-date for a stock metric is "today vs the same day last month".
    assert rollup["month_to_date"]["active_users"] == {"value": 500, "previous_value": 400, "change": 100, "change_percent": 25}


def test_null_when_a_required_day_in_the_range_is_missing():
    raw_by_date = _build_raw_by_date()
    del raw_by_date["2026-11-17"]  # inside both this week's and this month's range
    rollup = build_rollup("posthog", DATE, raw_by_date)
    assert rollup["week_to_date"]["new_trial_sign_ups"]["value"] is None
    assert rollup["month_to_date"]["new_trial_sign_ups"]["value"] is None
    # Last week / last month's ranges are untouched, so their comparisons still compute.
    assert rollup["week_to_date"]["new_trial_sign_ups"]["previous_value"] == 5
    assert rollup["month_to_date"]["new_trial_sign_ups"]["previous_value"] == 20


def test_clamps_month_to_date_into_a_shorter_previous_month():
    raw_by_date = {}
    current = "2026-02-01"
    while current <= "2026-03-31":
        raw_by_date[current] = {"new_trial_sign_ups": 1, "active_users": 1}
        current = add_london_calendar_days(current, 1)
    rollup = build_rollup("posthog", "2026-03-31", raw_by_date)
    # 1-31 March = 31 days; clamped previous-month range is 1-28 February = 28 days.
    assert rollup["month_to_date"]["new_trial_sign_ups"] == {
        "value": 31,
        "previous_value": 28,
        "change": 3,
        "change_percent": (3 / 28) * 100,
    }
