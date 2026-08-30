"""Wire-format helpers for Planbook API payloads."""

from __future__ import annotations

import datetime
import json
import re
from typing import Any

from .errors import UsageError

Payload = dict[str, Any]


def yn(value: bool) -> str:
    """Planbook booleans are the strings "Y" and "N"."""
    return "Y" if value else "N"


def intish(value: Any) -> str:
    """Integer fields must carry "0" when absent, never an empty string."""
    if value in (None, "", False):
        return "0"
    return str(int(value))


DAY_PREFIXES = {
    "monday": "m",
    "tuesday": "t",
    "wednesday": "w",
    "thursday": "r",
    "friday": "f",
    "saturday": "s",
    "sunday": "u",
}
DAY_LETTERS = {
    "M": "monday",
    "T": "tuesday",
    "W": "wednesday",
    "R": "thursday",
    "F": "friday",
    "S": "saturday",
    "U": "sunday",
}
TIME_RE = re.compile(r"^\s*(\d{1,2})[:.](\d{2})\s*([AaPp])?\.?[Mm]?\.?\s*$")


def parse_time(value: str | None) -> str:
    """Normalize a time to the 12-hour form Planbook stores.

    Planbook accepts only "9:00 AM"-style times. A 24-hour string is taken
    without complaint and stored as empty, so "14:30" would silently lose the
    lesson's time. Both forms are accepted here and converted.
    """
    if value is None or value == "":
        return ""
    match = TIME_RE.match(value)
    if not match:
        raise UsageError(
            f"Could not read {value!r} as a time. Use 9:00 AM, 9:00am, "
            "or 24-hour 14:30."
        )
    hour, minute, meridiem = int(match.group(1)), int(match.group(2)), match.group(3)
    if minute > 59:
        raise UsageError(f"{value!r} has an impossible minute.")
    if meridiem:
        if not 1 <= hour <= 12:
            raise UsageError(f"{value!r} has an impossible hour for AM/PM.")
        suffix = "AM" if meridiem.lower() == "a" else "PM"
    else:
        if hour > 23:
            raise UsageError(f"{value!r} has an impossible hour.")
        suffix = "AM" if hour < 12 else "PM"
        hour = hour % 12 or 12
    return f"{hour}:{minute:02d} {suffix}"


def parse_day_times(
    specs: list[str], days: list[str] | None
) -> dict[str, tuple[str, str]]:
    """Read --time values into {day: (start, end)}.

    Accepts "9:00-9:50" (every teaching day) or "M=9:00-9:50" (one day).
    """
    times: dict[str, tuple[str, str]] = {}
    for spec in specs or []:
        target, _, window = spec.rpartition("=")
        if "-" not in window:
            raise UsageError(
                f"--time {spec!r} needs a start and end, e.g. 9:00-9:50 or M=9:00-9:50."
            )
        start, _, end = window.partition("-")
        pair = (parse_time(start), parse_time(end))
        if not target and days is None:
            raise UsageError(
                f"--time {spec!r} applies to every teaching day, but no days "
                "were given. Name a day (M=9:00-9:50) or pass --days."
            )
        for day in parse_days(target) if target else days or []:
            times[day] = pair
    return times


def parse_days(spec: str) -> list[str]:
    """Turn a day spec like "MTWRF" into weekday names."""
    days: list[str] = []
    for char in spec.upper():
        if char not in DAY_LETTERS:
            raise UsageError(
                f"Unknown day letter {char!r} in {spec!r}. "
                "Use M T W R F S U (R=Thursday, U=Sunday)."
            )
        days.append(DAY_LETTERS[char])
    return days


DAY_ORDER = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]

# The schedule JSON indexes differently: teachDay1 is SUNDAY, not Monday. An
# off-by-one does not error, it silently shifts every day (Mon/Wed/Fri became
# Tue/Thu/Sun).
SCHEDULE_DAY_ORDER = [
    "sunday",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
]

# Rotations run up to 20 days, so all twenty slots are always sent; a weekly
# timetable fills the first seven and leaves the rest false.
SCHEDULE_SLOTS = 20


def edit_schedule(
    existing: list[dict[str, Any]],
    *,
    days: list[str] | None,
    times: dict[str, tuple[str, str]] | None,
) -> str:
    """Rebuild the `schedules` JSON from what the server already has.

    `getClass` returns `classSchedule` with all twenty rotation slots, plus
    `additionalClassDays` and any extra schedule rows a mid-year change
    created. Rebuilding from a blank template would flatten a rotating
    schedule into a plain week - silently, on something as innocent as a
    rename - so the existing rows are carried through and only the weekday
    slots the caller actually named are touched.
    """
    rows = []
    for index, row in enumerate(existing):
        slot: dict[str, Any] = {
            "scheduleStart": row.get("scheduleStart", ""),
            "additionalClassDays": row.get("additionalClassDays", []),
        }
        if "scheduleId" in row:
            slot["scheduleId"] = row["scheduleId"]
        last = index == len(existing) - 1
        for n in range(1, SCHEDULE_SLOTS + 1):
            day = SCHEDULE_DAY_ORDER[n - 1] if n <= len(SCHEDULE_DAY_ORDER) else None
            teaches = bool(row.get(f"day{n}Teach"))
            start = row.get(f"day{n}StartTime") or ""
            end = row.get(f"day{n}EndTime") or ""
            # Only the most recent row is edited; earlier rows are history.
            if last and day is not None:
                if days is not None:
                    teaches = day in days
                if times and day in times:
                    start, end = times[day]
                if not teaches:
                    start = end = ""
            slot[f"teachDay{n}"] = teaches
            slot[f"startDay{n}"] = start
            slot[f"endDay{n}"] = end
        rows.append(slot)
    return json.dumps(rows, separators=(",", ":"))


def build_schedule(
    days: list[str], start_date: str, times: dict[str, tuple[str, str]] | None = None
) -> str:
    """Build a fresh `schedules` JSON for a new class."""
    times = times or {}
    slot: dict[str, Any] = {"scheduleStart": start_date, "additionalClassDays": []}
    for index in range(1, SCHEDULE_SLOTS + 1):
        day = (
            SCHEDULE_DAY_ORDER[index - 1] if index <= len(SCHEDULE_DAY_ORDER) else None
        )
        teaches = bool(day and day in days)
        start, end = times.get(day or "", ("", ""))
        slot[f"teachDay{index}"] = teaches
        slot[f"startDay{index}"] = start if teaches else ""
        slot[f"endDay{index}"] = end if teaches else ""
    return json.dumps([slot], separators=(",", ":"))


def parse_date(value: str, *, flag: str = "date") -> str:
    """Validate an MM/DD/YYYY date and return it unchanged.

    Worth doing locally: the server answers a malformed date with a Java
    NullPointerException about `Schedule.getScheduleStart()`, which tells a
    caller nothing and arrives as an API error rather than a usage error.
    """
    try:
        month, day, year = (int(part) for part in value.split("/"))
        datetime.date(year, month, day)
    except ValueError:
        raise UsageError(
            f"{flag}: {value!r} is not a date. Planbook wants MM/DD/YYYY, "
            "e.g. 09/03/2026."
        ) from None
    if not 1000 <= year <= 9999:
        raise UsageError(f"{flag}: {value!r} needs a four-digit year.")
    return value
