"""Domain operations, with Planbook's abbreviated field names translated.

The wire format uses keys like `cId`, `cN`, `mSt`, so everything leaving this
module is renamed. `--raw` bypasses the translation when you need to see
exactly what the server said.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .client import PlanbookClient, intish, yn
from .errors import PlanbookError, SchemaDrift, UsageError

# Single-letter day prefixes: `r` is Thursday and `u` is Sunday - the second
# letter of the name, not the first.
DAY_PREFIXES = {
    "monday": "m",
    "tuesday": "t",
    "wednesday": "w",
    "thursday": "r",
    "friday": "f",
    "saturday": "s",
    "sunday": "u",
}

DAY_LETTERS = {"M": "monday", "T": "tuesday", "W": "wednesday",
               "R": "thursday", "F": "friday", "S": "saturday", "U": "sunday"}


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


def parse_day_times(specs: list[str],
                    days: list[str] | None) -> dict[str, tuple[str, str]]:
    """Read --time values into {day: (start, end)}.

    Accepts "9:00-9:50" (every teaching day) or "M=9:00-9:50" (one day).
    """
    times: dict[str, tuple[str, str]] = {}
    for spec in specs or []:
        target, _, window = spec.rpartition("=")
        if "-" not in window:
            raise UsageError(
                f"--time {spec!r} needs a start and end, e.g. 9:00-9:50 "
                "or M=9:00-9:50."
            )
        start, _, end = window.partition("-")
        pair = (parse_time(start), parse_time(end))
        if not target and days is None:
            raise UsageError(
                f"--time {spec!r} applies to every teaching day, but no days "
                "were given. Name a day (M=9:00-9:50) or pass --days."
            )
        for day in (parse_days(target) if target else days or []):
            times[day] = pair
    return times


def parse_days(spec: str) -> list[str]:
    """Turn a day spec like "MTWRF" into weekday names."""
    days = []
    for char in spec.upper():
        if char not in DAY_LETTERS:
            raise UsageError(
                f"Unknown day letter {char!r} in {spec!r}. "
                "Use M T W R F S U (R=Thursday, U=Sunday)."
            )
        days.append(DAY_LETTERS[char])
    return days


def normalize_class(raw: Any) -> dict[str, Any]:
    """Map one wire-format class record to readable keys."""
    if not isinstance(raw, dict):
        raise SchemaDrift(
            f"Expected a class object, got {type(raw).__name__}. "
            "The API shape may have changed."
        )
    schedule = {}
    for day, prefix in DAY_PREFIXES.items():
        # "Y"/"N" strings: a raw "N" is truthy in Python and would read as
        # "teaches on Sunday".
        schedule[day] = {
            "teaches": str(raw.get(f"{prefix}T", "")).upper() == "Y",
            "start": raw.get(f"{prefix}St"),
            "end": raw.get(f"{prefix}Et"),
        }
    return {
        "id": raw.get("cId"),
        "name": raw.get("cN"),
        "start_date": raw.get("cSd"),
        "end_date": raw.get("cEd"),
        "color": raw.get("cC"),
        "year_id": raw.get("cYId"),
        "description": raw.get("classDesc"),
        "lesson_layout_id": raw.get("lessonLayoutId"),
        "teacher_id": raw.get("teacherId"),
        "district_id": raw.get("districtId"),
        "units": raw.get("units"),
        "schedule": schedule,
    }


def list_classes(client: PlanbookClient, *, raw: bool = False) -> dict[str, Any]:
    body = client.post("/getClasses2")
    client.require(body, "classes", "currentYearId", where="getClasses2")
    if raw:
        return body
    records = body.get("classes") or []
    if not isinstance(records, list):
        raise SchemaDrift("getClasses2 returned a non-list `classes`.")
    return {
        "current_year_id": body.get("currentYearId"),
        "classes": [normalize_class(c) for c in records],
        "lesson_banks": body.get("lessonBanks"),
        "district_lesson_banks": body.get("districtLessonBanks"),
    }


# Weekday order for the *_Teach form fields.
DAY_ORDER = ["monday", "tuesday", "wednesday", "thursday", "friday",
             "saturday", "sunday"]

# The schedule JSON indexes differently: teachDay1 is SUNDAY, not Monday. An
# off-by-one does not error, it silently shifts every day (Mon/Wed/Fri became
# Tue/Thu/Sun).
SCHEDULE_DAY_ORDER = ["sunday", "monday", "tuesday", "wednesday", "thursday",
                      "friday", "saturday"]

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


def build_schedule(days: list[str], start_date: str,
                   times: dict[str, tuple[str, str]] | None = None) -> str:
    """Build a fresh `schedules` JSON for a new class."""
    times = times or {}
    slot: dict[str, Any] = {"scheduleStart": start_date, "additionalClassDays": []}
    for index in range(1, SCHEDULE_SLOTS + 1):
        day = (SCHEDULE_DAY_ORDER[index - 1]
               if index <= len(SCHEDULE_DAY_ORDER) else None)
        teaches = bool(day and day in days)
        start, end = times.get(day or "", ("", ""))
        slot[f"teachDay{index}"] = teaches
        slot[f"startDay{index}"] = start if teaches else ""
        slot[f"endDay{index}"] = end if teaches else ""
    return json.dumps([slot], separators=(",", ":"))


def _class_payload(
    *,
    name: str,
    start_date: str,
    end_date: str,
    days: list[str],
    color: str,
    description: str,
    times: dict[str, tuple[str, str]] | None = None,
    lesson_layout_id: Any = 0,
) -> dict[str, str]:
    """Shared body for creating and updating a class.

    Booleans here are "Y"/"N". "true"/"false" is accepted without complaint
    and silently produces a class that teaches on no days at all.
    """
    payload: dict[str, str] = {
        "className": name,
        "classStartDate": start_date,
        "classEndDate": end_date,
        "color": color,
        "classDesc": description,
        "titleColor": "#000000",
        "titleSize": "12",
        "titleFont": "Arial",
        "classLabelBold": yn(False),
        "classLabelItalic": yn(False),
        "classLabelUnderline": yn(False),
        "noStudents": yn(True),
        "useSchoolStart": yn(False),
        "useSchoolEnd": yn(False),
        "updateNoClass": yn(True),
        "shiftLessons": "false",
        "scheduleChange": "false",
        "source": "",
        "sourceId": "0",
        "sourceSettings[connectStudents]": "true",
        "sourceSettings[connectAssignments]": "true",
        "sourceSettings[connectGrades]": "true",
        "userMode": "T",
        "collaborateType": "0",
        "collaborateSubjectId": "0",
        "collaborateKey": "",
        "lessonLayoutId": intish(lesson_layout_id),
        "schedules": build_schedule(days, start_date, times),
        # "true" validates and commits nothing. Same trap as events.
        "verifyShift": "false",
    }
    for day in DAY_ORDER:
        payload[f"{day}Teach"] = yn(day in days)
    return payload


def create_class(
    client: PlanbookClient | None,
    *,
    name: str,
    start_date: str,
    end_date: str,
    days: list[str],
    color: str = "#7ED321",
    description: str = "",
    times: dict[str, tuple[str, str]] | None = None,
    lesson_layout_id: Any = 0,
    dry_run: bool = False,
) -> dict[str, Any]:
    payload = _class_payload(name=name, start_date=start_date, end_date=end_date,
                             days=days, color=color, description=description,
                             times=times, lesson_layout_id=lesson_layout_id)
    if dry_run:
        return {"dry_run": True, "endpoint": "/addClass", "payload": payload}

    # /addClass does not report the id it created, and matching by name
    # afterwards breaks the moment two classes share a name. Diff the ids
    # instead.
    before = {str(c.get("cId")) for c in
              (client.post("/getClasses2") or {}).get("classes") or []}
    client.post("/addClass", payload)
    after = (client.post("/getClasses2") or {}).get("classes") or []
    created = [c for c in after if str(c.get("cId")) not in before]
    result: dict[str, Any] = {"ok": True, "name": name, "days": days}
    if len(created) == 1:
        result["class_id"] = created[0].get("cId")
    else:
        result["class_id"] = None
        result["note"] = (
            "Could not identify the new class id "
            f"({len(created)} classes appeared). Run `planbook classes list`."
        )
    return result


def update_class(
    client: PlanbookClient,
    *,
    class_id: Any,
    name: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    days: list[str] | None = None,
    color: str | None = None,
    description: str | None = None,
    times: dict[str, tuple[str, str]] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Update a class, changing only what you pass.

    Reads the class first and edits that. The endpoint replaces the whole
    record, so a payload built from defaults would wipe the description,
    colour, lesson layout and per-day times of anything it did not restate.

    `/updateClass/v10` is the versioned path the app calls; plain
    `/updateClass` also answers. `scheduleChange=true` is required or the
    new schedule is discarded while the rest of the update succeeds.
    """
    current = get_class(client, class_id)
    if not isinstance(current, dict) or "className" not in current:
        raise SchemaDrift(
            f"getClass({class_id}) did not return a class record. "
            "Cannot update without reading the current values first."
        )
    schedule_rows = current.get("classSchedule")
    if not isinstance(schedule_rows, list) or not schedule_rows:
        raise SchemaDrift(
            f"getClass({class_id}) returned no classSchedule. Updating without "
            "it would erase the class's teaching days."
        )

    def flag(value: Any) -> str:
        if isinstance(value, bool):
            return yn(value)
        return yn(str(value).upper() == "Y")

    # The schedule rows are authoritative for which days are taught; the
    # scalar <day>Teach fields are a flattened view of the latest row.
    latest = schedule_rows[-1]
    current_days = [
        day for n, day in enumerate(SCHEDULE_DAY_ORDER, start=1)
        if latest.get(f"day{n}Teach")
    ]
    new_days = days if days is not None else current_days
    start = start_date or current.get("classStartDate") or ""

    payload: dict[str, str] = {
        "classId": intish(class_id),
        "className": name if name is not None else current.get("className", ""),
        "classStartDate": start,
        "classEndDate": end_date or current.get("classEndDate") or "",
        "color": color if color is not None else current.get("color") or "#7ED321",
        "classDesc": (description if description is not None
                      else current.get("classDesc") or ""),
        "titleColor": current.get("titleColor") or "#000000",
        "titleSize": str(current.get("titleSize") or "12"),
        "titleFont": current.get("titleFont") or "Arial",
        "classLabelBold": flag(current.get("classLabelBold")),
        "classLabelItalic": flag(current.get("classLabelItalic")),
        "classLabelUnderline": flag(current.get("classLabelUnderline")),
        "noStudents": flag(current.get("noStudents")),
        "useSchoolStart": flag(current.get("useSchoolStart")),
        "useSchoolEnd": flag(current.get("useSchoolEnd")),
        "lessonLayoutId": intish(current.get("lessonLayoutId")),
        "source": current.get("source") or "",
        "sourceId": intish(current.get("sourceId")),
        "collaborateType": intish(current.get("collaborateType")),
        "collaborateSubjectId": intish(current.get("collaborateSubjectId")),
        "collaborateKey": current.get("collaborateKey") or "",
        "sourceSettings[connectStudents]": "true",
        "sourceSettings[connectAssignments]": "true",
        "sourceSettings[connectGrades]": "true",
        "updateNoClass": yn(True),
        "shiftLessons": "false",
        "userMode": "T",
        "schedules": edit_schedule(schedule_rows, days=days, times=times),
        "scheduleChange": "true",
        "verifyShift": "false",
    }
    for day in DAY_ORDER:
        payload[f"{day}Teach"] = yn(day in new_days)

    if dry_run:
        return {"dry_run": True, "endpoint": "/updateClass/v10", "payload": payload}
    client.post("/updateClass/v10", payload)
    return {"ok": True, "class_id": payload["classId"],
            "name": payload["className"], "days": new_days}


def get_class(client: PlanbookClient, class_id: Any) -> Any:
    return client.post("/getClass", {"classId": intish(class_id)})


def delete_class(client: PlanbookClient, *, class_id: Any) -> dict[str, Any]:
    """Delete a class and every lesson in it. There is no undo."""
    client.post("/deleteClass", {"classId": intish(class_id)})
    return {"ok": True, "deleted_class_id": intish(class_id)}


def delete_lesson(
    client: PlanbookClient | None,
    *,
    class_id: Any,
    date: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    payload = {"classId": intish(class_id), "customDate": date, "userMode": "T"}
    if dry_run:
        return {"dry_run": True, "endpoint": "/deleteLesson", "payload": payload}
    client.post("/deleteLesson", payload)
    return {"ok": True, "class_id": payload["classId"], "date": date}


def no_school_dates(client: PlanbookClient) -> set[str]:
    """Dates the calendar marks as no-school.

    Advisory only, so every failure is swallowed: a warning that cannot be
    computed must never stop the write it was meant to annotate.
    """
    dates: set[str] = set()
    try:
        for event in list_events(client, limit=1000) or []:
            if event.get("noSchool"):
                for key in ("eventDate", "eventCurrentDate"):
                    if event.get(key):
                        dates.add(str(event[key]))
    except Exception:
        return set()
    return dates


def set_lesson(
    client: PlanbookClient | None,
    *,
    class_id: int | str,
    date: str,
    title: str | None = None,
    text: str | None = None,
    homework: str | None = None,
    notes: str | None = None,
    unit_id: Any = None,
    start_time: str | None = None,
    end_time: str | None = None,
    sections: dict[int, str] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Create or update the lesson for one class on one date.

    `/updateLesson` is addressed by class + date, not lesson id, so this is an
    upsert. `client` may be None under `dry_run`: inspecting a payload should
    never require a session.
    """
    updated = []
    if title is not None:
        updated.append("LESSONTITLE")
    if text is not None:
        updated.append("LESSONTEXT")
    if homework is not None:
        updated.append("HOMEWORKTEXT")
    if notes is not None:
        updated.append("NOTESTEXT")
    if (start_time is None) != (end_time is None):
        raise UsageError(
            "Pass --start-time and --end-time together. The server stores them "
            "as a pair, so sending one alone clears the other."
        )
    if start_time is not None:
        updated.extend(["CUSTOMSTART", "CUSTOMEND"])
    section_text = dict(sections or {})
    for index in section_text:
        updated.append(SECTION_FIELDS[index].upper())
    if not updated:
        raise UsageError(
            "Nothing to write. Pass at least one of --title, --text, "
            "--homework, --notes, --start-time, --end-time."
        )

    payload = {
        "classId": intish(class_id),
        "customDate": date,
        "unitId": intish(unit_id),
        "extraLesson": "0",
        "lessonId": "0",
        "linkedLessonId": "0",
        "lessonTitle": title or "",
        "lessonText": section_text.get(1, text or ""),
        "homeworkText": section_text.get(2, homework or ""),
        "notesText": section_text.get(3, notes or ""),
        "tab4Text": section_text.get(4, ""),
        "tab5Text": section_text.get(5, ""),
        "tab6Text": section_text.get(6, ""),
        "addClassDaysCode": "",
        "customStart": parse_time(start_time),
        "customEnd": parse_time(end_time),
        "lessonLock": yn(False),
        "isEditingALinkedLesson": yn(False),
        "strategySent": yn(True),
        "unitStandardsSent": yn(True),
        "statusesSent": yn(True),
        "schoolWorks": "[]",
        "updatedFields": ",".join(updated),
        "oldLesson": "",
        "fetchDay": "true",
    }
    if dry_run:
        return {"dry_run": True, "endpoint": "/updateLesson", "payload": payload}
    assert client is not None
    client.post("/updateLesson", payload)
    return {"ok": True, "class_id": payload["classId"], "date": date,
            "updated_fields": updated}


def special_days(
    client: PlanbookClient, *, teacher_id: Any, year_id: Any, school_id: Any = 0
) -> Any:
    return client.post(
        "/getSpecialDays",
        {
            "teacherId": intish(teacher_id),
            "yearId": intish(year_id),
            "schoolId": intish(school_id),
        },
    )


def get_week(client: PlanbookClient, *, monday: str, weeks: int = 1) -> Any:
    """Fetch lessons and events starting from a Monday.

    Only partially mapped - `days` is keyed by integer offset, not date, and
    the lesson payload inside is undecoded. Output is passed through raw.
    See docs/API-NOTES.md ("Open").
    """
    return client.post(
        "/getLessonsEvents",
        {"monday": monday, "userMode": "T", "fetchWeekSize": str(weeks)},
    )


# A lesson has six text sections. The first three have fixed names; tabs 4-6
# are named and enabled per lesson layout, and are "Not Used" until someone
# configures them.
SECTION_FIELDS = {
    1: "lessonText",
    2: "homeworkText",
    3: "notesText",
    4: "tab4Text",
    5: "tab5Text",
    6: "tab6Text",
}
DEFAULT_SECTION_LABELS = {1: "Lesson", 2: "Homework", 3: "Notes"}


def lesson_sections(client: PlanbookClient) -> list[dict[str, Any]]:
    """The six lesson sections with their current labels and enabled state."""
    conf = settings(client)
    if not isinstance(conf, dict):
        raise SchemaDrift("getSettings did not return an object.")
    out = []
    for index, field in SECTION_FIELDS.items():
        label = conf.get(f"tab{index}Label") or DEFAULT_SECTION_LABELS.get(index)
        enabled = str(conf.get(f"tab{index}Enabled", "Y")).upper() != "N"
        out.append({
            "section": index,
            "label": label or f"Tab {index}",
            "enabled": enabled if index > 3 else True,
            "field": field,
        })
    return out


def resolve_section(sections: list[dict[str, Any]], key: str) -> int:
    """Map a section number or label to its index."""
    key = key.strip()
    if key.isdigit():
        index = int(key)
        if index in SECTION_FIELDS:
            return index
        raise UsageError(f"Lesson sections are numbered 1-6; got {key!r}.")
    for section in sections:
        if str(section["label"]).lower() == key.lower():
            return int(section["section"])
    names = ", ".join(f'{s["section"]}={s["label"]!r}' for s in sections)
    raise UsageError(f"No lesson section called {key!r}. Available: {names}")


def settings(client: PlanbookClient) -> Any:
    return client.post("/getSettings")


def standards(client: PlanbookClient) -> Any:
    return client.post("/getStandards")


# Read-only endpoints taking no arguments.  name -> (path, key to unwrap)
SIMPLE_READS: dict[str, tuple[str, str | None]] = {
    "assignments": ("/getAssignments", "assignments"),
    "assessments": ("/getAssessments", "assessments"),
    "schools": ("/getSchools", "schools"),
    "templates": ("/services/planbook/template/get", "templates"),
    "notes": ("/services/planbook/newNote/filterNotes", None),
    "students": ("/services/planbook/student/getAllFromSchool", None),
    "standards-report": ("/getStandardsReport", None),
    "comments": ("/getCommentsTo", None),
}


def simple_read(
    client: PlanbookClient, name: str, *, raw: bool = False, extra: dict | None = None
) -> Any:
    """Fetch one of the argument-free read endpoints.

    Most wrap a single array in a single key; that envelope is unwrapped
    unless `raw`, so callers get the list rather than something to dig through.
    """
    path, unwrap = SIMPLE_READS[name]
    body = client.post(path, extra or {})
    if raw or unwrap is None or not isinstance(body, dict):
        return body
    if unwrap in body and len(body) == 1:
        return body[unwrap]
    return body


def attachments(client: PlanbookClient, *, teacher_id: Any) -> Any:
    return client.post(
        "/getAttachmentList",
        {
            "teacherId": intish(teacher_id),
            "isFolderStructured": "true",
            "withAllFolders": "true",
        },
    )


# ---------------------------------------------------------------------------
# Events
#
# Update and delete want the *whole* event echoed back, not just its id, so
# mutations look the record up first: the server treats missing fields as
# cleared, and a skeleton delete removes the wrong occurrence of a repeat.

EVENT_TYPES = '["Teacher","School","District"]'
EVENT_SCHEDULES = '["School","NoSchool"]'


def list_events(
    client: PlanbookClient,
    *,
    start: str = "",
    end: str = "",
    limit: int = 75,
    search: str = "",
) -> Any:
    body = client.post(
        "/getEvents",
        {
            "userMode": "T",
            "currentSchoolId": "0",
            "start": start,
            "end": end,
            "limit": str(limit),
            "searchText": search,
            "showEventTypes": EVENT_TYPES,
            "showEventSchedules": EVENT_SCHEDULES,
        },
    )
    if isinstance(body, dict) and set(body) == {"events"}:
        return body["events"]
    return body


def _event_payload(
    event: dict[str, Any], *, current_date: str | None = None, shift: str = "N"
) -> dict[str, str]:
    """Flatten an event record into the form fields the server expects.

    Three fields fail silently when wrong - the server answers `{"events": []}`
    with no error and does nothing:

      eventCurrentDate  empty when creating; the occurrence date when deleting
      shiftLessons      "N" when creating; "false" when deleting
      verifyShift       "true" only runs a conflict check and commits nothing;
                        the app sends "true" then "false" to confirm
    """
    return {
        "eventId": intish(event.get("eventId") or event.get("id")),
        "googleId": event.get("googleId") or "",
        "googleCalendarId": event.get("googleCalendarId") or "",
        "customEventId": intish(event.get("customEventId")),
        "eventDate": event.get("eventDate") or "",
        "endDate": event.get("endDate") or event.get("eventDate") or "",
        "repeats": event.get("repeats") or "daily",
        "eventText": event.get("eventText") or "",
        "eventStartTime": parse_time(event.get("eventStartTime")),
        "eventEndTime": parse_time(event.get("eventEndTime")),
        "eventTitle": event.get("eventTitle") or "",
        "eventCurrentDate": current_date if current_date is not None else "",
        "specialDayId": intish(event.get("specialDayId")),
        "schoolId": intish(event.get("schoolId")),
        "districtId": intish(event.get("districtId")),
        "noSchool": "true" if event.get("noSchool") else "false",
        "noCycle": "true" if event.get("noCycle") else "false",
        "privateFlag": "true" if event.get("privateFlag") else "false",
        "shiftLessons": shift,
        # "false" means commit. See the note above.
        "verifyShift": "false",
        "stickerId": intish(event.get("stickerId")),
        "limit": "75",
        "userMode": "T",
    }


def create_event(
    client: PlanbookClient,
    *,
    title: str,
    date: str,
    end_date: str | None = None,
    text: str = "",
    start_time: str = "",
    end_time: str = "",
    private: bool = False,
    no_school: bool = False,
    repeats: str = "daily",
    dry_run: bool = False,
) -> Any:
    payload = _event_payload({
        "repeats": repeats,
        "eventTitle": title,
        "eventDate": date,
        "endDate": end_date or date,
        "eventText": text,
        "eventStartTime": start_time,
        "eventEndTime": end_time,
        "privateFlag": private,
        "noSchool": no_school,
    })
    payload["updatedFields"] = "extraDays"
    payload["updateCurrentEvent"] = "false"
    if dry_run:
        return {"dry_run": True, "endpoint": "/addEvent", "payload": payload}
    client.post("/addEvent", payload)
    return {"ok": True, "title": title, "date": date}


def find_event(client: PlanbookClient, event_id: Any) -> dict[str, Any]:
    wanted = str(event_id)
    # No date window: the server's default range would hide events outside it
    # and this would report "no such event" for one that exists.
    for event in list_events(client, start="", end="", limit=1000) or []:
        if str(event.get("eventId") or event.get("id")) == wanted:
            return event
    raise UsageError(f"No event with id {event_id}. Run `planbook events list`.")


def delete_event(
    client: PlanbookClient,
    *,
    event_id: Any,
    occurrence_only: bool = False,
    dry_run: bool = False,
) -> Any:
    """Delete an event.

    By default this removes the whole series. `occurrence_only` drops just
    the one date, which matters for a repeating event.
    """
    event = find_event(client, event_id)
    payload = _event_payload(
        event,
        current_date=event.get("eventCurrentDate") or event.get("eventDate") or "",
        shift="false",
    )
    payload["deleteCurrentEvent"] = "true" if occurrence_only else "false"
    payload["currentSchoolId"] = "0"
    if dry_run:
        return {"dry_run": True, "endpoint": "/deleteEvent", "payload": payload}
    client.post("/deleteEvent", payload)
    return {"ok": True, "deleted_event_id": payload["eventId"],
            "title": payload["eventTitle"],
            "scope": "occurrence" if occurrence_only else "series"}


# ---------------------------------------------------------------------------
# Units
#
# All three operations go through /updateUnit, selected by `action` (A/U/D).
# `subjectId` is the class id - Planbook says "subject" here and nowhere else.

UNIT_ACTIONS = {"add": "A", "update": "U", "delete": "D"}


def _unit_payload(
    *,
    action: str,
    class_id: Any,
    unit_id: Any = 0,
    number: str = "",
    title: str = "",
    description: str = "",
    start: str = "",
    end: str = "",
    lesson_text: str = "",
    homework_text: str = "",
    notes_text: str = "",
    sections: dict[int, str] | None = None,
) -> dict[str, str]:
    section_text = dict(sections or {})
    return {
        "unitId": intish(unit_id),
        "subjectId": intish(class_id),
        "unitNum": number,
        "unitTitle": title,
        "action": action,
        "unitDesc": description,
        "unitStart": start,
        "unitEnd": end,
        "unitLessonText": section_text.get(1, lesson_text),
        "unitHomeworkText": section_text.get(2, homework_text),
        "unitNotesText": section_text.get(3, notes_text),
        "unitSection4Text": section_text.get(4, ""),
        "unitSection5Text": section_text.get(5, ""),
        "unitSection6Text": section_text.get(6, ""),
        "userMode": "T",
        "types": "SS",
    }


def list_units(client: PlanbookClient, *, raw: bool = False) -> Any:
    body = client.post("/getUnits")
    if raw or not isinstance(body, dict):
        return body
    return body.get("units", body)


def create_unit(
    client: PlanbookClient | None,
    *,
    class_id: Any,
    number: str,
    title: str,
    description: str = "",
    start: str = "",
    end: str = "",
    dry_run: bool = False,
) -> Any:
    payload = _unit_payload(action="A", class_id=class_id, number=number,
                            title=title, description=description,
                            start=start, end=end)
    if dry_run:
        return {"dry_run": True, "endpoint": "/updateUnit", "payload": payload}
    client.post("/updateUnit", payload)
    return {"ok": True, "class_id": payload["subjectId"], "number": number,
            "title": title}


def update_unit(
    client: PlanbookClient | None,
    *,
    unit_id: Any,
    class_id: Any,
    number: str,
    title: str,
    description: str = "",
    start: str = "",
    end: str = "",
    dry_run: bool = False,
) -> Any:
    payload = _unit_payload(action="U", class_id=class_id, unit_id=unit_id,
                            number=number, title=title, description=description,
                            start=start, end=end)
    if dry_run:
        return {"dry_run": True, "endpoint": "/updateUnit", "payload": payload}
    client.post("/updateUnit", payload)
    return {"ok": True, "unit_id": payload["unitId"], "title": title}


def delete_unit(
    client: PlanbookClient | None,
    *,
    unit_id: Any,
    class_id: Any,
    dry_run: bool = False,
) -> Any:
    payload = _unit_payload(action="D", class_id=class_id, unit_id=unit_id)
    if dry_run:
        return {"dry_run": True, "endpoint": "/updateUnit", "payload": payload}
    client.post("/updateUnit", payload)
    return {"ok": True, "deleted_unit_id": payload["unitId"]}


# ---------------------------------------------------------------------------
# To-dos
#
# Creating one takes two calls, as the web app does: action "A" mints an empty
# row and returns its id, then "U" fills it in. There is no single-shot create.

TODO_PRIORITIES = {"low": "1", "medium": "2", "high": "3"}


def list_todos(client: PlanbookClient, *, class_id: str = "all") -> Any:
    body = client.post("/getToDos", {"classId": class_id})
    if isinstance(body, dict) and set(body) == {"toDos"}:
        return body["toDos"]
    return body


def _todo_payload(
    *,
    todo_id: Any,
    text: str,
    start: str,
    due: str,
    priority: str,
    done: bool,
    repeats: str = "daily",
) -> dict[str, str]:
    return {
        "startDate": start,
        "dueDate": due or start,
        "toDoText": text,
        "priority": TODO_PRIORITIES.get(priority, priority),
        "done": "1" if done else "0",
        "toDoId": intish(todo_id),
        "repeats": repeats,
        "currentDate": "",
        "updateCurrentTodo": "false",
        "action": "U",
    }


def create_todo(
    client: PlanbookClient,
    *,
    text: str,
    start: str,
    due: str = "",
    priority: str = "low",
    done: bool = False,
    repeats: str = "daily",
) -> dict[str, Any]:
    created = client.post("/updateToDo", {"action": "A"})
    todo_id = None
    if isinstance(created, dict):
        todo_id = created.get("toDoId")
    if not todo_id:
        raise SchemaDrift(
            "Creating a to-do did not return a toDoId. "
            f"Response was: {created!r}"
        )
    payload = _todo_payload(todo_id=todo_id, text=text, start=start, due=due,
                            priority=priority, done=done, repeats=repeats)
    try:
        client.post("/updateToDo", payload)
    except PlanbookError:
        # Step one already created an empty row. Leaving it behind would put
        # a blank to-do in the user's list with no sign of where it came from.
        try:
            delete_todo(client, todo_id=todo_id)
        except PlanbookError:
            pass
        raise
    return {"ok": True, "todo_id": todo_id, "text": text}


def update_todo(
    client: PlanbookClient,
    *,
    todo_id: Any,
    text: str,
    start: str,
    due: str = "",
    priority: str = "low",
    done: bool = False,
    repeats: str = "daily",
) -> dict[str, Any]:
    client.post("/updateToDo", _todo_payload(
        todo_id=todo_id, text=text, start=start, due=due,
        priority=priority, done=done, repeats=repeats))
    return {"ok": True, "todo_id": intish(todo_id)}


def delete_todo(client: PlanbookClient, *, todo_id: Any) -> dict[str, Any]:
    client.post("/updateToDo", {"toDoId": intish(todo_id), "action": "D"})
    return {"ok": True, "deleted_todo_id": intish(todo_id)}
