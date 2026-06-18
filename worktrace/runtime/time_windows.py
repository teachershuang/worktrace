from __future__ import annotations

from datetime import datetime, time

from worktrace.config.settings import WorkPeriod


def is_within_work_periods(now: datetime, periods: list[WorkPeriod]) -> bool:
    current = time(hour=now.hour, minute=now.minute)
    return any(period.contains(current) for period in periods)
