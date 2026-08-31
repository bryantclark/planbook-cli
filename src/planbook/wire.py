"""Wire-format helpers for Planbook API payloads."""

from __future__ import annotations

import datetime
import json
import re

from .errors import UsageError
from .narrow import flag as truthy
from .types import JsonObject, JsonValue


def yn(value: bool) -> str:
    """Planbook booleans are the strings "Y" and "N"."""
    return "Y" if value else "N"


def intish(value: JsonValue) -> str:
    """Integer fields must carry "0" when absent, never an empty string."""
    if value in (None, "", False):
        return "0"
    if not isinstance(value, int | float | str):
        raise UsageError(f"Expected an id, got {type(value).__name__}.")
    return str(int(value))


#: To-do priority, name -> wire value.
TODO_PRIORITIES = {"low": "1", "medium": "2", "high": "3"}
PRIORITY_NAMES = {v: k for k, v in TODO_PRIORITIES.items()}

#: The six unit section texts, in section order.
UNIT_SECTION_FIELDS = {
    1: "unitLessonText",
    2: "unitHomeworkText",
    3: "unitNotesText",
    4: "unitSection4Text",
    5: "unitSection5Text",
    6: "unitSection6Text",
}

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

    Planbook takes a 24-hour string without complaint and stores it empty, so
    "14:30" would silently lose the lesson's time.
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

# The schedule JSON indexes from Sunday: teachDay1 is SUNDAY, not Monday. An
# off-by-one does not error, it silently shifts every day.
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
    existing: list[JsonObject],
    *,
    days: list[str] | None,
    times: dict[str, tuple[str, str]] | None,
) -> str:
    """Rebuild the `schedules` JSON from what the server already has.

    Building from a blank template would silently flatten a rotating schedule
    into a plain week, so existing rows are carried through and only the
    weekday slots the caller named are touched.
    """
    rows = []
    for index, row in enumerate(existing):
        slot: JsonObject = {
            "scheduleStart": row.get("scheduleStart", ""),
            "additionalClassDays": row.get("additionalClassDays", []),
        }
        if "scheduleId" in row:
            slot["scheduleId"] = row["scheduleId"]
        last = index == len(existing) - 1
        for n in range(1, SCHEDULE_SLOTS + 1):
            day = SCHEDULE_DAY_ORDER[n - 1] if n <= len(SCHEDULE_DAY_ORDER) else None
            teaches = truthy(row.get(f"day{n}Teach"))
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
    slot: JsonObject = {"scheduleStart": start_date, "additionalClassDays": []}
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
    """Validate a date and return it zero-padded as MM/DD/YYYY.

    The server answers a malformed date with a Java NullPointerException about
    `Schedule.getScheduleStart()`, so the check is worth doing locally.

    The padding matters: the server reports dates zero-padded and `find_lesson`
    matches them by exact string, so `9/3/2026` would miss the lesson saved on
    `09/03/2026` and the write would blank it.
    """
    if not isinstance(value, str):
        raise UsageError(
            f"{flag}: expected a date string, got {type(value).__name__}. "
            "Planbook wants MM/DD/YYYY, e.g. 09/03/2026."
        )
    parts = value.split("/")
    try:
        if len(parts) != 3:
            raise ValueError
        month, day, year = (int(part) for part in parts)
        datetime.date(year, month, day)
    except ValueError:
        raise UsageError(
            f"{flag}: {value!r} is not a date. Planbook wants MM/DD/YYYY, "
            "e.g. 09/03/2026."
        ) from None
    if not 1000 <= year <= 9999:
        raise UsageError(f"{flag}: {value!r} needs a four-digit year.")
    return f"{month:02d}/{day:02d}/{year:04d}"
