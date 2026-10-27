"""Pure schedule calculations for the private weekly intake job."""

from __future__ import annotations

from datetime import date


def scheduled_week(local_date: date, week_one: date) -> int | None:
    """Return the NFL week for a local date, or None outside Weeks 2-18."""
    elapsed_days = (local_date - week_one).days
    if elapsed_days < 0:
        return None
    week = elapsed_days // 7 + 1
    return week if 2 <= week <= 18 else None
