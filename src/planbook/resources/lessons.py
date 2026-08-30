"""Lesson resource operations."""

from __future__ import annotations

import contextlib
import datetime
import json
from collections.abc import Iterator
from typing import Any

from ..client import PlanbookClient
from ..errors import SchemaDrift, UsageError
from ..wire import Payload, intish, parse_date, yn
from .misc import list_assignments, settings


def delete_lesson(
    client: PlanbookClient,
    *,
    class_id: Any,
    date: str,
) -> dict[str, Any]:
    payload = {"classId": intish(class_id), "customDate": date, "userMode": "T"}
    client.post("/deleteLesson", payload)
    return {"ok": True, "class_id": payload["classId"], "date": date}


def no_school_dates(client: PlanbookClient) -> set[str]:
    """Dates the calendar marks as no-school.

    Advisory only, so every failure is swallowed: a warning that cannot be
    computed must never stop the write it was meant to annotate.
    """
    dates: set[str] = set()
    try:
        from .events import list_events

        for event in list_events(client, limit=1000) or []:
            if event.get("noSchool"):
                for key in ("eventDate", "eventCurrentDate"):
                    if event.get(key):
                        dates.add(str(event[key]))
    except Exception:
        return set()
    return dates


def iter_days(body: Any) -> Iterator[dict[str, Any]]:
    """Yield each day in a getLessonsEvents response.

    Lessons carry no date of their own - the date comes from the day they sit
    in. Each day has `date`, `dayOfWeek` and `objects`, and `objects` holds a
    placeholder for every class whether or not a lesson was saved.
    """
    days = body.get("days") if isinstance(body, dict) else None
    if not isinstance(days, list):
        raise SchemaDrift("getLessonsEvents returned no `days` list.")
    for day in days:
        if isinstance(day, dict) and day.get("date"):
            yield day


def read_week(
    client: PlanbookClient, *, monday: str, weeks: int = 1, saved_only: bool = True
) -> list[dict[str, Any]]:
    """Lessons for a week, grouped by date."""
    body = client.post(
        "/getLessonsEvents",
        {"monday": monday, "userMode": "T", "fetchWeekSize": str(weeks)},
    )
    out = []
    for day in iter_days(body):
        lessons = [
            {
                "class_id": obj.get("classId"),
                "class_name": obj.get("className"),
                "lesson_id": obj.get("lessonId"),
                "title": (obj.get("lessonText") and obj.get("lessonTitle"))
                or obj.get("lessonTitle"),
                "start": obj.get("startTime"),
                "end": obj.get("endTime"),
                "text": obj.get("lessonText"),
                "homework": obj.get("homeworkText"),
                "notes": obj.get("notesText"),
                "standards": [st.get("id") for st in (obj.get("standards") or [])],
                "assignments": [
                    a.get("assignmentTitle") for a in (obj.get("assignments") or [])
                ],
                "attachments": [
                    a.get("filename") for a in (obj.get("attachments") or [])
                ],
            }
            for obj in (day.get("objects") or [])
            if isinstance(obj, dict)
            and (obj.get("lessonId") or not saved_only)
            and obj.get("classId")
        ]
        out.append(
            {
                "date": day["date"],
                "day_of_week": day.get("dayOfWeek"),
                "lessons": lessons,
            }
        )
    return out


def find_lesson(
    client: PlanbookClient, *, class_id: Any, date: str
) -> dict[str, Any] | None:
    """The saved lesson for one class on one date, or None."""
    body = client.post(
        "/getLessonsEvents",
        {"monday": date, "userMode": "T", "fetchWeekSize": "1"},
    )
    wanted = str(intish(class_id))
    for day in iter_days(body):
        if day["date"] != date:
            continue
        for obj in day.get("objects") or []:
            if (
                isinstance(obj, dict)
                and str(obj.get("classId")) == wanted
                and obj.get("lessonId")
            ):
                return obj
    return None


def _yn_of(value: Any) -> str:
    """Normalise a flag that may arrive as a bool or as "Y"/"N"."""
    if isinstance(value, bool):
        return yn(value)
    return yn(str(value).upper() == "Y")


def _html(value: Any) -> str:
    """Text fields come back as strings or None; normalise for re-sending."""
    return "" if value is None else str(value)


def lesson_payload(
    *,
    class_id: int | str,
    date: str,
    title: str | None = None,
    text: str | None = None,
    homework: str | None = None,
    notes: str | None = None,
    unit_id: Any = None,
    sections: dict[int, str] | None = None,
    standards: list[str] | None = None,
    assignments: list[Any] | None = None,
    attach: list[dict[str, str]] | None = None,
) -> tuple[Payload, list[str]]:
    """Build the form payload and the list of fields it updates.

    Pure: building a payload never needs a session, which is what lets
    --dry-run work offline.
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
    section_text = dict(sections or {})
    for index in section_text:
        updated.append(SECTION_FIELDS[index].upper())
    if standards is not None:
        updated.append("STANDARDS")
    if assignments is not None:
        updated.append("SCHOOLWORKS")
    if attach is not None:
        updated.append("ATTACHMENTS")
    if not updated:
        raise UsageError(
            "Nothing to write. Pass at least one of --title, --text, "
            "--homework, --notes, --section, --standard, --assignment, --attach."
        )

    payload: dict[str, Any] = {
        "classId": intish(class_id),
        # Checked here rather than only in argparse so bulk items get it too.
        "customDate": parse_date(date),
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
        # Sent because the server rejects the form without them; a lesson
        # always keeps its class period's times. See docs/API-NOTES.md.
        "customStart": "",
        "customEnd": "",
        "lessonLock": yn(False),
        "isEditingALinkedLesson": yn(False),
        "strategySent": yn(True),
        "unitStandardsSent": yn(True),
        "statusesSent": yn(True),
        "updatedFields": ",".join(updated),
        "oldLesson": "",
        "fetchDay": "true",
    }
    if attach is not None:
        # Repeated triples, one per file. The lesson stores the signed URL,
        # not a reference, so the link survives independently of the
        # resource list.
        payload["attachmentNames"] = [a["name"] for a in attach] or [""]
        payload["attachmentURL"] = [a["url"] for a in attach] or [""]
        payload["attachmentPrivate"] = ["N" for _ in attach] or [""]

    if standards is not None:
        # Repeated form fields, not a comma list - a comma-joined value is
        # accepted and clears the set instead. Sending the ids replaces
        # whatever was attached, so pass the full set you want.
        payload["standardDBIds"] = [str(s) for s in standards] or [""]
    if assignments is not None:
        # Only sent when the caller named assignments. Sending "[]" otherwise
        # detaches whatever the lesson already had, so a plain rename used to
        # silently drop them.
        payload["schoolWorks"] = json.dumps(
            [
                {
                    "type": "ASSIGNMENT",
                    "typeId": int(a),
                    "shortValueText": "",
                    "longValueText": 0,
                }
                for a in assignments
            ],
            separators=(",", ":"),
        )
    return payload, updated


def set_lesson(
    client: PlanbookClient,
    *,
    class_id: int | str,
    date: str,
    title: str | None = None,
    text: str | None = None,
    homework: str | None = None,
    notes: str | None = None,
    unit_id: Any = None,
    sections: dict[int, str] | None = None,
    standards: list[str] | None = None,
    assignments: list[Any] | None = None,
    attach: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Create or update the lesson for one class on one date.

    `/updateLesson` is keyed by class and date rather than lesson id, so this
    is an upsert: writing the same date twice edits in place.
    """
    # The server does NOT honour updatedFields as a mask: any text field sent
    # empty is written empty. Verified by losing a title, body and homework to
    # a call that only attached a standard. So every write is
    # read-modify-write, and anything the caller did not name is carried over.
    existing = find_lesson(client, class_id=class_id, date=date)
    carry: dict[str, Any] = {}
    if existing:
        title = title if title is not None else _html(existing.get("lessonTitle"))
        text = text if text is not None else _html(existing.get("lessonText"))
        homework = (
            homework if homework is not None else _html(existing.get("homeworkText"))
        )
        notes = notes if notes is not None else _html(existing.get("notesText"))
        if unit_id is None:
            unit_id = existing.get("unitId")
        carried = {
            index: _html(existing.get(field))
            for index, field in SECTION_FIELDS.items()
            if index >= 4 and existing.get(field)
        }
        if carried:
            sections = {**carried, **(sections or {})}
        # Flags the payload would otherwise reset to their defaults.
        carry = {
            "lessonLock": _yn_of(existing.get("lessonLock")),
            "extraLesson": intish(existing.get("extraLesson")),
            "linkedLessonId": intish(existing.get("linkedLessonId")),
            "isEditingALinkedLesson": _yn_of(existing.get("isEditingALinkedLesson")),
        }

    payload, updated = lesson_payload(
        class_id=class_id,
        date=date,
        title=title,
        text=text,
        homework=homework,
        notes=notes,
        unit_id=unit_id,
        sections=sections,
        standards=standards,
        assignments=assignments,
        attach=attach,
    )
    # Flags the fresh payload would otherwise reset on an existing lesson.
    payload.update(carry)

    if assignments:
        # Assignments belong to a class. Attaching one from a different class
        # is accepted and silently does nothing.
        known = {
            str(a.get("assignmentId")): a for a in (list_assignments(client) or [])
        }
        for ident in assignments:
            record = known.get(str(ident))
            if record is None:
                raise UsageError(
                    f"No assignment with id {ident}. See `planbook assignments`."
                )
            if str(record.get("subjectId")) != str(intish(class_id)):
                raise UsageError(
                    f"Assignment {ident} belongs to class "
                    f"{record.get('subjectId')} ({record.get('className')}), not "
                    f"{intish(class_id)}. Assignments cannot cross classes."
                )

    if standards is not None or assignments is not None or attach is not None:
        # Standards, assignments and attachments only attach to a lesson that already
        # exists; on a brand-new date the id is 0 and the server drops them.
        existing = find_lesson(client, class_id=class_id, date=date)
        if existing is None:
            client.post(
                "/updateLesson", dict(payload, standardDBIds="", schoolWorks="[]")
            )
            existing = find_lesson(client, class_id=class_id, date=date)
        if existing and existing.get("lessonId"):
            payload["lessonId"] = str(existing["lessonId"])

    client.post("/updateLesson", payload)
    result: dict[str, Any] = {
        "ok": True,
        "class_id": payload["classId"],
        "date": date,
        "updated_fields": updated,
    }
    if standards is not None:
        result["standards"] = standards
    if assignments is not None:
        result["assignments"] = assignments
    if attach is not None:
        result["attachments"] = [a["name"] for a in attach]
    return result


def get_week(client: PlanbookClient, *, monday: str, weeks: int = 1) -> Any:
    """The undecoded `/getLessonsEvents` body for a week starting on a Monday.

    Backs `lessons week --raw`. `read_week` is the decoded form; this keeps
    the fields it drops.
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
        out.append(
            {
                "section": index,
                "label": label or f"Tab {index}",
                "enabled": enabled if index > 3 else True,
                "field": field,
            }
        )
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
    names = ", ".join(f"{s['section']}={s['label']!r}" for s in sections)
    raise UsageError(f"No lesson section called {key!r}. Available: {names}")


def lessons_between(
    client: PlanbookClient, *, start: str, end: str
) -> list[dict[str, Any]]:
    """Saved lessons falling on or between two dates."""
    weeks = 1
    with contextlib.suppress(ValueError):
        weeks = max(1, (_as_date(end) - _as_date(start)).days // 7 + 2)
    found = []
    for day in read_week(client, monday=start, weeks=weeks):
        # Compare dates, not MM/DD/YYYY strings: lexically "01/05/2027" sorts
        # before "12/22/2026", so a winter-break range matched nothing and the
        # no-school guard reported zero lessons at risk.
        try:
            in_range = _as_date(start) <= _as_date(day["date"]) <= _as_date(end)
        except ValueError:
            in_range = day["date"] == start
        if in_range:
            found.extend(day["lessons"])
    return found


def _as_date(value: str) -> datetime.date:
    month, day, year = (int(part) for part in value.split("/"))
    return datetime.date(year, month, day)
