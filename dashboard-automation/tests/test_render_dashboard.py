from pathlib import Path
from unittest.mock import patch

import render_dashboard
from render_dashboard import (
    _empty_week_month,
    _format_weekday_date,
    _map_insights,
    _pence_to_pounds,
    _read_competitors,
    _with_reason,
)


def test_pence_to_pounds_converts_both_periods():
    week_month = {"week": {"cur": 3996, "prev": 2997}, "month": {"cur": None, "prev": 14985}}
    assert _pence_to_pounds(week_month) == {"week": {"cur": 39.96, "prev": 29.97}, "month": {"cur": None, "prev": 149.85}}


def test_empty_week_month_is_all_null():
    assert _empty_week_month() == {"week": {"cur": None, "prev": None}, "month": {"cur": None, "prev": None}}


def test_format_weekday_date():
    # 2026-11-23 is a Monday (verified independently in dateUtils' own tests).
    assert _format_weekday_date("2026-11-23") == "Monday 23/11/2026"


def test_with_reason_fills_in_text_from_status():
    section = _with_reason({"status": "on", "value": 5})
    assert section["reason"] == "On target - nothing needs attention here right now."
    assert section["value"] == 5


def test_map_insights_handles_no_insight_doc():
    assert _map_insights(None) == []


def test_map_insights_handles_no_flags():
    assert _map_insights({"status": "skipped_no_flags", "actions": []}) == []


def test_map_insights_maps_title_and_detail_into_one_text():
    insight_doc = {"status": "generated", "actions": [{"title": "Chase failed payments", "detail": "One card declined yesterday."}]}
    mapped = _map_insights(insight_doc)
    assert len(mapped) == 1
    assert mapped[0]["t"] == "Chase failed payments. One card declined yesterday."
    assert mapped[0]["p"] == "Medium"


def test_read_competitors_missing_file_returns_empty_lists(tmp_path):
    with patch.object(render_dashboard, "DASHBOARD_HTML_DIR", tmp_path):
        assert _read_competitors() == {"competitors": [], "influencers": [], "updated": None}


def test_read_competitors_reads_real_reference_file():
    # The real data/config/competitors.json is hand-maintained reference data
    # (see social-research-brief-nov-dec-2026.md) - just check the shape, not
    # the exact content, so this doesn't break every time it's updated.
    result = _read_competitors()
    assert isinstance(result["competitors"], list) and len(result["competitors"]) > 0
    assert isinstance(result["influencers"], list) and len(result["influencers"]) > 0
    assert all({"name", "platform", "link"} <= entry.keys() for entry in result["competitors"])
