"""Formatting helpers, GBP and UK English throughout."""

from __future__ import annotations


def format_pence(pence: float) -> str:
    """Formats whole pence as GBP, e.g. 123456 -> "£1,234.56"."""
    pounds = pence / 100
    return f"£{pounds:,.2f}"


def format_count(n: float) -> str:
    """Thousands-separated whole number, UK English."""
    return f"{round(n):,}"
