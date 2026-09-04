"""Wire-format parsing: dates, times, day letters and the schedule grid."""

import json

import pytest

from planbook.errors import UsageError
from planbook.wire import (
    build_schedule,
    parse_date,
    parse_day_times,
    parse_days,
    parse_time,
)


def test_parse_days_weekdays_and_special_letters():
    assert parse_days("MTWRF") == [
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
    ]
    assert parse_days("RU") == ["thursday", "sunday"]


def test_parse_days_rejects_unknown_letter():
    with pytest.raises(UsageError):
        parse_days("X")


def test_build_schedule_indexes_from_sunday():
    # teachDay1 is Sunday, not Monday; an off-by-one silently shifts every day.
    slot = json.loads(build_schedule(["monday", "wednesday", "friday"], "08/31/2026"))[
        0
    ]
    assert slot["teachDay1"] is False  # Sunday
    assert slot["teachDay2"] is True  # Monday
    assert slot["teachDay4"] is True  # Wednesday
    assert slot["teachDay6"] is True  # Friday
    assert slot["teachDay7"] is False  # Saturday
    assert slot["scheduleStart"] == "08/31/2026"


def test_parse_time_accepts_24h_and_12h():
    # Planbook stores only 12-hour times; a 24-hour string is accepted on the
    # wire and stored as empty, silently losing the time.
    assert parse_time("14:30") == "2:30 PM"
    assert parse_time("09:00") == "9:00 AM"
    assert parse_time("9:00am") == "9:00 AM"
    assert parse_time("9:00 AM") == "9:00 AM"
    assert parse_time("") == ""
    assert parse_time(None) == ""


def test_parse_time_handles_noon_and_midnight():
    assert parse_time("12:00") == "12:00 PM"
    assert parse_time("00:15") == "12:15 AM"
    assert parse_time("12:00 AM") == "12:00 AM"


def test_parse_time_rejects_nonsense():
    for bad in ("9:5", "25:00", "10:99", "lunchtime"):
        with pytest.raises(UsageError):
            parse_time(bad)


def test_parse_day_times_whole_week_and_per_day():
    assert parse_day_times(["9:00-9:50"], ["monday", "friday"]) == {
        "monday": ("9:00 AM", "9:50 AM"),
        "friday": ("9:00 AM", "9:50 AM"),
    }
    assert parse_day_times(["M=8:00-8:45", "W=13:00-13:50"], []) == {
        "monday": ("8:00 AM", "8:45 AM"),
        "wednesday": ("1:00 PM", "1:50 PM"),
    }


def test_build_schedule_carries_per_day_times():
    slot = json.loads(
        build_schedule(["monday"], "08/31/2026", {"monday": ("9:00 AM", "9:50 AM")})
    )[0]
    assert slot["startDay2"] == "9:00 AM"  # teachDay2 is Monday
    assert slot["endDay2"] == "9:50 AM"
    assert slot["startDay3"] == ""  # Tuesday, not taught


def test_parse_date_rejects_what_the_server_answers_with_a_null_pointer():
    # An impossible date used to reach Planbook, which replied with a Java NPE
    # about Schedule.getScheduleStart() - an API error, not a usage error.
    assert parse_date("09/03/2026") == "09/03/2026"
    # Zero-padded so it matches the server's format on find_lesson's exact
    # string compare; an unpadded date used to miss the saved lesson and blank
    # it on write.
    assert parse_date("9/3/2026") == "09/03/2026"
    assert parse_date("12/1/2026") == "12/01/2026"
    for bad in ("13/45/2026", "notadate", "2026-09-03", "09/31/2026", "9/3/26"):
        with pytest.raises(UsageError):
            parse_date(bad)


def test_parse_date_rejects_a_non_string_instead_of_crashing():
    # A bulk item with a null date must be a usage error, not an AttributeError
    # escaping main() as a traceback.
    for bad in (None, 123, ["x"]):
        with pytest.raises(UsageError):
            parse_date(bad)  # type: ignore[arg-type]
