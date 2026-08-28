"""Domain operations, with Planbook's abbreviated field names translated.

The wire format uses keys like `cId`, `cN`, `mSt`. Those are fine for a
browser bundle and hostile to anyone reading a terminal, so everything that
leaves this module uses readable names. `--raw` on the CLI bypasses the
translation when you need to see exactly what the server said.
"""

from __future__ import annotations

from typing import Any

from .client import PlanbookClient, intish, yn
from .errors import UsageError

# Planbook's single-letter day prefixes. `r` is Thursday and `u` is Sunday -
# both are the second letter of their name, not the first.
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


def normalize_class(raw: dict[str, Any]) -> dict[str, Any]:
    """Map one wire-format class record to readable keys."""
    schedule = {}
    for day, prefix in DAY_PREFIXES.items():
        schedule[day] = {
            "teaches": raw.get(f"{prefix}T"),
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
    return {
        "current_year_id": body.get("currentYearId"),
        "classes": [normalize_class(c) for c in body.get("classes") or []],
        "lesson_banks": body.get("lessonBanks"),
        "district_lesson_banks": body.get("districtLessonBanks"),
    }


def create_class(
    client: PlanbookClient,
    *,
    name: str,
    start_date: str,
    end_date: str,
    days: list[str],
    color: str = "#7ED321",
    description: str = "",
) -> dict[str, Any]:
    """Create a class. Mirrors the fields the web UI sends to /addClass."""
    payload: dict[str, Any] = {
        "className": name,
        "classStartDate": start_date,
        "classEndDate": end_date,
        "color": color,
        "classDesc": description,
        "titleColor": "#000000",
        "titleSize": "12",
        "titleFont": "Arial",
        "classLabelBold": "false",
        "classLabelItalic": "false",
        "classLabelUnderline": "false",
        "noStudents": "true",
        "useSchoolStart": "false",
        "useSchoolEnd": "false",
        "updateNoClass": "false",
        "shiftLessons": "false",
        "scheduleChange": "false",
        "source": "",
        "sourceId": "0",
    }
    for day in DAY_PREFIXES:
        payload[f"{day}Teach"] = "true" if day in days else "false"
        payload[f"wk2{day}Teach"] = "false"
    return client.post("/addClass", payload)


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
    dry_run: bool = False,
) -> dict[str, Any]:
    """Create or update the lesson for one class on one date.

    `/updateLesson` is addressed by class + date, not by lesson id, so this
    is an upsert: calling it twice for the same date edits in place rather
    than creating a duplicate.

    `client` may be None when `dry_run` is set, so that building and
    inspecting a payload never requires a session.
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
    if not updated:
        raise UsageError(
            "Nothing to write. Pass at least one of --title, --text, "
            "--homework, --notes."
        )

    payload = {
        "classId": intish(class_id),
        "customDate": date,
        "unitId": intish(unit_id),
        "extraLesson": "0",
        "lessonId": "0",
        "linkedLessonId": "0",
        "lessonTitle": title or "",
        "lessonText": text or "",
        "homeworkText": homework or "",
        "notesText": notes or "",
        "tab4Text": "",
        "tab5Text": "",
        "tab6Text": "",
        "addClassDaysCode": "",
        "customStart": "",
        "customEnd": "",
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
    """Holidays and other non-teaching days for a school year."""
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

    NOTE: the response shape is only partially mapped. It returns a `days`
    object keyed by integer offset rather than by date, and the lesson
    payload inside it has not been fully decoded. Output is passed through
    unmodified - treat it as raw. See docs/API-NOTES.md ("Open").
    """
    return client.post(
        "/getLessonsEvents",
        {"monday": monday, "userMode": "T", "fetchWeekSize": str(weeks)},
    )


def settings(client: PlanbookClient) -> Any:
    return client.post("/getSettings")


def standards(client: PlanbookClient) -> Any:
    return client.post("/getStandards")


# Read-only endpoints that need no argument handling beyond an optional
# teacher id. Table-driven because the interesting part is the endpoint list,
# not fourteen near-identical functions.
#
#   name -> (path, required-fields-builder or None, response key to unwrap)
SIMPLE_READS: dict[str, tuple[str, str | None]] = {
    "units": ("/getUnits", "units"),
    "todos": ("/getToDos", None),
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

    Returns the whole body under `--raw`, or the meaningful list when the
    response is a single-key envelope - most of these wrap one array in one
    key, and unwrapping it is the difference between output an agent can use
    directly and output it has to dig through.
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
# Events are addressed by id, and both update and delete want the *whole*
# event echoed back, not just the id. So mutations look the record up first
# rather than sending a skeleton: the server treats missing fields as
# cleared, and a delete built from a skeleton silently deletes the wrong
# occurrence of a repeating event.

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

    Two fields differ between creating and deleting, and getting them wrong
    fails silently - the server returns `{"events": []}` with no error and
    simply does not create the event:

      eventCurrentDate  empty when creating; the occurrence date when deleting
      shiftLessons      "N" when creating; "false" when deleting

    `verifyShift` is the one that really bites. With "true" the server runs a
    conflict check and commits nothing, answering `{"events": []}` exactly as
    if it had succeeded. The web app sends "true" first and re-sends "false"
    to confirm; a client that only ever sends "true" silently writes nothing.
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
        "eventStartTime": event.get("eventStartTime") or "",
        "eventEndTime": event.get("eventEndTime") or "",
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
    dry_run: bool = False,
) -> Any:
    payload = _event_payload({
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
    for event in list_events(client, limit=500) or []:
        if str(event.get("eventId") or event.get("id")) == wanted:
            return event
    raise UsageError(f"No event with id {event_id}. Run `planbook events list`.")


def delete_event(
    client: PlanbookClient, *, event_id: Any, dry_run: bool = False
) -> Any:
    event = find_event(client, event_id)
    payload = _event_payload(
        event,
        current_date=event.get("eventCurrentDate") or event.get("eventDate") or "",
        shift="false",
    )
    payload["deleteCurrentEvent"] = "false"
    payload["currentSchoolId"] = "0"
    if dry_run:
        return {"dry_run": True, "endpoint": "/deleteEvent", "payload": payload}
    client.post("/deleteEvent", payload)
    return {"ok": True, "deleted_event_id": payload["eventId"],
            "title": payload["eventTitle"]}
