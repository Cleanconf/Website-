from date_utils import add_london_calendar_days
from rules import DEFAULT_TARGETS_CONFIG, flag_all_metrics, flag_metric, seven_day_average, status_word

DATE = "2026-11-20"


def _seven_flat_days_before(date_str: str, value: float) -> dict:
    return {add_london_calendar_days(date_str, -i): {"revenue_pence": value} for i in range(1, 8)}


def test_seven_day_average_excludes_the_date_itself():
    raw_by_date = _seven_flat_days_before(DATE, 1000)
    raw_by_date[DATE] = {"revenue_pence": 999_999}  # should not affect the average
    assert seven_day_average(raw_by_date, DATE, "revenue_pence") == 1000


def test_seven_day_average_null_if_any_day_missing():
    raw_by_date = _seven_flat_days_before(DATE, 1000)
    del raw_by_date[add_london_calendar_days(DATE, -3)]
    assert seven_day_average(raw_by_date, DATE, "revenue_pence") is None


def test_flag_metric_flags_a_higher_is_better_metric_down_past_threshold():
    flag = flag_metric("stripe", "revenue_pence", 8000, 10_000, DEFAULT_TARGETS_CONFIG)
    assert flag is not None
    assert "down 20.0%" in flag["reason"]


def test_flag_metric_does_not_flag_within_threshold():
    assert flag_metric("stripe", "revenue_pence", 9000, 10_000, DEFAULT_TARGETS_CONFIG) is None


def test_flag_metric_does_not_flag_an_upward_move_for_higher_is_better():
    assert flag_metric("stripe", "revenue_pence", 15_000, 10_000, DEFAULT_TARGETS_CONFIG) is None


def test_flag_metric_flags_a_lower_is_better_metric_up_past_threshold():
    flag = flag_metric("stripe", "churned_subscriptions", 10, 5, DEFAULT_TARGETS_CONFIG)
    assert flag is not None
    assert "up 100.0%" in flag["reason"]


def test_flag_metric_never_flags_a_zero_average():
    assert flag_metric("stripe", "failed_payments", 5, 0, DEFAULT_TARGETS_CONFIG) is None


def test_flag_metric_never_flags_missing_values():
    assert flag_metric("stripe", "revenue_pence", None, 10_000, DEFAULT_TARGETS_CONFIG) is None
    assert flag_metric("stripe", "revenue_pence", 8000, None, DEFAULT_TARGETS_CONFIG) is None


def test_flag_all_metrics_only_flags_what_moved():
    raw_by_date = _seven_flat_days_before(DATE, 1000)
    raw_by_date[DATE] = {"revenue_pence": 500, "new_paid_sign_ups": 3}
    for i in range(1, 8):
        raw_by_date[add_london_calendar_days(DATE, -i)]["new_paid_sign_ups"] = 3
    flags = flag_all_metrics("stripe", DATE, raw_by_date, {"revenue_pence": "sum", "new_paid_sign_ups": "sum"}, DEFAULT_TARGETS_CONFIG)
    assert [f["metric"] for f in flags] == ["revenue_pence"]


def test_flag_all_metrics_empty_when_todays_snapshot_is_missing():
    raw_by_date = _seven_flat_days_before(DATE, 1000)
    assert flag_all_metrics("stripe", DATE, raw_by_date, {"revenue_pence": "sum"}, DEFAULT_TARGETS_CONFIG) == []


def test_status_word_on_target_when_real_target_met():
    assert status_word(120, 100, 100, "higher_is_better", 0.15) == "On target"


def test_status_word_watch_when_just_short_of_target():
    assert status_word(95, 100, 100, "higher_is_better", 0.15) == "Watch"


def test_status_word_off_target_when_far_short():
    assert status_word(50, 100, 100, "higher_is_better", 0.15) == "Off target"


def test_status_word_falls_back_to_seven_day_average_without_a_target():
    assert status_word(1000, 1000, None, "higher_is_better", 0.15) == "On target"
    assert status_word(800, 1000, None, "higher_is_better", 0.15) == "Watch"
    assert status_word(500, 1000, None, "higher_is_better", 0.15) == "Off target"


def test_status_word_watch_when_no_value_at_all():
    assert status_word(None, 1000, None, "higher_is_better", 0.15) == "Watch"
