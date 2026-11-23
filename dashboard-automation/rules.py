"""Flags metrics that moved against their target direction, and the status word shown next to each headline number."""

from __future__ import annotations

from date_utils import add_london_calendar_days

DEFAULT_TARGETS_CONFIG = {
    "flag_threshold_fraction": 0.15,
    "targets": {
        "revenue_pence": {"target": None, "direction": "higher_is_better"},
        "new_paid_sign_ups": {"target": None, "direction": "higher_is_better"},
        "churned_subscriptions": {"target": None, "direction": "lower_is_better"},
        "failed_payments": {"target": None, "direction": "lower_is_better"},
        "new_trial_sign_ups": {"target": None, "direction": "higher_is_better"},
    },
}


def seven_day_average(raw_by_date: dict, date_str: str, key: str) -> float | None:
    """The average of `key` over the 7 days strictly before `date_str`. `None` if any of those 7 days has no usable snapshot."""
    total = 0
    for i in range(1, 8):
        raw = raw_by_date.get(add_london_calendar_days(date_str, -i))
        if raw is None or key not in raw:
            return None
        total += raw[key]
    return total / 7


def flag_metric(source: str, key: str, current_value: float | None, average: float | None, config: dict) -> dict | None:
    """
    Flags a metric that has moved against its target direction by more than
    the configured fraction of its 7-day average (the brief's example: "down
    more than 15% vs the 7-day average"). `None` when there's nothing to
    flag - including when the average is exactly 0, where a percentage move
    isn't meaningful.
    """
    if current_value is None or average is None or average == 0:
        return None

    direction = config["targets"].get(key, {}).get("direction", "higher_is_better")
    change_fraction = (current_value - average) / average
    is_adverse = change_fraction < 0 if direction == "higher_is_better" else change_fraction > 0
    if not is_adverse or abs(change_fraction) <= config["flag_threshold_fraction"]:
        return None

    word = "down" if change_fraction < 0 else "up"
    return {
        "source": source,
        "metric": key,
        "comparison": {
            "value": current_value,
            "previous_value": average,
            "change": current_value - average,
            "change_percent": change_fraction * 100,
        },
        "reason": f"{key} is {word} {abs(change_fraction * 100):.1f}% vs its 7-day average",
    }


def flag_all_metrics(source: str, date_str: str, raw_by_date: dict, metric_kinds: dict, config: dict) -> list[dict]:
    """Runs `flag_metric` over every metric a source defines, for Claude's insights step."""
    today_raw = raw_by_date.get(date_str)
    if not today_raw:
        return []
    flags = []
    for key in metric_kinds:
        flag = flag_metric(source, key, today_raw.get(key), seven_day_average(raw_by_date, date_str, key), config)
        if flag:
            flags.append(flag)
    return flags


def status_word(current_value: float | None, average: float | None, target: float | None, direction: str, threshold_fraction: float) -> str:
    """
    The status word shown next to a headline number (never colour alone).
    With a real target configured, status is how far today's value is from
    it, in the target's direction. Until a target is set (every metric
    starts as a placeholder - see DEFAULT_TARGETS_CONFIG), this falls back
    to the 7-day-average flag instead: genuinely anomalous reads "Watch" or
    "Off target", everything else reads "On target". That fallback is a
    judgement call, not a real target comparison - worth checking before
    the first live Slack post, since it decides what "On target" means for
    every metric that doesn't have a real target yet.
    """
    if current_value is None:
        return "Watch"

    if target is not None and target != 0:
        gap_fraction = (current_value - target) / target
        on_target = gap_fraction >= 0 if direction == "higher_is_better" else gap_fraction <= 0
        if on_target:
            return "On target"
        return "Off target" if abs(gap_fraction) > threshold_fraction * 2 else "Watch"

    if average is None or average == 0:
        return "Watch"
    change_fraction = (current_value - average) / average
    is_adverse = change_fraction < 0 if direction == "higher_is_better" else change_fraction > 0
    if not is_adverse:
        return "On target"
    return "Off target" if abs(change_fraction) > threshold_fraction * 2 else "Watch"
