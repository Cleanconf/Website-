"""
UK 2026 DST transitions (verified by weekday calculation, not assumed):
clocks forward Sunday 29 March 2026 at 01:00 UTC; back Sunday 25 October
2026 at 01:00 UTC.
"""

from datetime import datetime, timezone

from date_utils import (
    add_london_calendar_days,
    is_london_month_start,
    london_day_range_utc,
    london_month_label,
    london_month_start,
    london_week_start,
    same_london_day_last_month,
    same_london_weekday_last_week,
    to_london_date_string,
    yesterday_london,
)


def test_to_london_date_string_matches_utc_in_winter():
    assert to_london_date_string(datetime(2026, 1, 15, 23, 30, tzinfo=timezone.utc)) == "2026-01-15"


def test_to_london_date_string_is_an_hour_ahead_in_summer():
    assert to_london_date_string(datetime(2026, 7, 15, 23, 30, tzinfo=timezone.utc)) == "2026-07-16"


def test_london_day_range_utc_normal_24_hour_range():
    start, end = london_day_range_utc("2026-01-15")
    assert start.isoformat() == "2026-01-15T00:00:00+00:00"
    assert end.isoformat() == "2026-01-16T00:00:00+00:00"


def test_london_day_range_utc_23_hour_spring_forward_day():
    start, end = london_day_range_utc("2026-03-29")
    assert start.isoformat() == "2026-03-29T00:00:00+00:00"
    assert end.isoformat() == "2026-03-29T23:00:00+00:00"
    assert (end - start).total_seconds() == 23 * 3600


def test_london_day_range_utc_25_hour_autumn_fallback_day():
    start, end = london_day_range_utc("2026-10-25")
    assert start.isoformat() == "2026-10-24T23:00:00+00:00"
    assert end.isoformat() == "2026-10-26T00:00:00+00:00"
    assert (end - start).total_seconds() == 25 * 3600


def test_london_day_range_utc_normal_day_after_transition():
    start, end = london_day_range_utc("2026-10-26")
    assert start.isoformat() == "2026-10-26T00:00:00+00:00"
    assert end.isoformat() == "2026-10-27T00:00:00+00:00"


def test_add_london_calendar_days():
    assert add_london_calendar_days("2026-03-29", 1) == "2026-03-30"
    assert add_london_calendar_days("2026-10-25", 1) == "2026-10-26"
    assert add_london_calendar_days("2026-01-01", -1) == "2025-12-31"


def test_yesterday_london_winter():
    assert yesterday_london(datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc)) == "2026-11-19"


def test_yesterday_london_summer_near_midnight_utc():
    # 23:30 UTC is already 00:30 the next day in BST.
    assert yesterday_london(datetime(2026, 7, 1, 23, 30, tzinfo=timezone.utc)) == "2026-07-01"


def test_london_week_start_on_a_sunday():
    assert london_week_start("2026-03-29") == "2026-03-23"


def test_london_week_start_unchanged_on_a_monday():
    assert london_week_start("2026-03-23") == "2026-03-23"


def test_same_london_weekday_last_week():
    assert same_london_weekday_last_week("2026-11-20") == "2026-11-13"


def test_london_month_start():
    assert london_month_start("2026-11-20") == "2026-11-01"


def test_same_london_day_last_month_clamps_into_shorter_february():
    assert same_london_day_last_month("2026-03-31") == "2026-02-28"


def test_same_london_day_last_month_no_clamp_needed():
    assert same_london_day_last_month("2026-05-15") == "2026-04-15"


def test_same_london_day_last_month_rolls_back_a_year():
    assert same_london_day_last_month("2026-01-15") == "2025-12-15"


def test_london_month_label():
    assert london_month_label("2026-11-20") == "2026-11"


def test_is_london_month_start():
    assert is_london_month_start("2026-11-01") is True
    assert is_london_month_start("2026-11-02") is False
