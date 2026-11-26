"""Time metadata shared by signal and comment ingestion."""

from datetime import date, datetime, timedelta, timezone


MARKET_TIMEZONE = timezone(timedelta(hours=8))
LEGACY_DATE_SOURCE = "legacy_archive_date"


def observed_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def market_today() -> date:
    return datetime.now(MARKET_TIMEZONE).date()


def epoch_time(value) -> str:
    try:
        stamp = int(value or 0)
        return datetime.fromtimestamp(stamp, timezone.utc).isoformat() if stamp > 0 else ""
    except (TypeError, ValueError, OSError, OverflowError):
        return ""


def newest_results(candidates, limit):
    """Sample (result, UTC timestamp) pairs, keeping source order for unknown dates."""
    now = observed_now()
    return sorted(
        candidates,
        key=lambda candidate: candidate[1] if candidate[1] <= now else "",
        reverse=True,
    )[:limit]


def source_time(value: str) -> tuple[str, str]:
    """Keep date-only values distinct from timestamps with an explicit offset."""
    value = (value or "").strip()
    try:
        if len(value) == 10:
            return date.fromisoformat(value).isoformat(), "date"
        if "T" not in value and " " not in value:
            return "", "unknown"
        stamp = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
        if stamp.tzinfo is not None:
            return stamp.isoformat(), "timestamp"
    except ValueError:
        pass
    return "", "unknown"


def source_day(value: str) -> str:
    value, precision = source_time(value)
    if precision == "timestamp":
        return datetime.fromisoformat(value).astimezone(MARKET_TIMEZONE).date().isoformat()
    return value


TIME_COLUMNS = {
    "source_published_at": "",
    "published_time_source": "",
    "published_time_precision": "unknown",
    "observed_at": "",
    "first_seen": "",
    "last_seen": "",
}
