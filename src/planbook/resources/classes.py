"""Class resource operations."""

from __future__ import annotations

from typing import Any, cast

from ..client import PlanbookClient
from ..errors import SchemaDrift
from ..wire import (
    DAY_ORDER,
    DAY_PREFIXES,
    SCHEDULE_DAY_ORDER,
    build_schedule,
    edit_schedule,
    intish,
    yn,
)


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
        return cast(dict[str, Any], body)
    records = body.get("classes") or []
    if not isinstance(records, list):
        raise SchemaDrift("getClasses2 returned a non-list `classes`.")
    return {
        "current_year_id": body.get("currentYearId"),
        "classes": [normalize_class(c) for c in records],
        "lesson_banks": body.get("lessonBanks"),
        "district_lesson_banks": body.get("districtLessonBanks"),
    }


def class_payload(
    *,
    name: str,
    start_date: str,
    end_date: str,
    days: list[str],
    color: str = "#7ED321",
    description: str = "",
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
    client: PlanbookClient,
    *,
    name: str,
    start_date: str,
    end_date: str,
    days: list[str],
    color: str = "#7ED321",
    description: str = "",
    times: dict[str, tuple[str, str]] | None = None,
    lesson_layout_id: Any = 0,
) -> dict[str, Any]:
    payload = class_payload(
        name=name,
        start_date=start_date,
        end_date=end_date,
        days=days,
        color=color,
        description=description,
        times=times,
        lesson_layout_id=lesson_layout_id,
    )

    # /addClass does not report the id it created, and matching by name
    # afterwards breaks the moment two classes share a name. Diff the ids
    # instead.
    before = {
        str(c.get("cId"))
        for c in (client.post("/getClasses2") or {}).get("classes") or []
    }
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
        day
        for n, day in enumerate(SCHEDULE_DAY_ORDER, start=1)
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
        "classDesc": (
            description if description is not None else current.get("classDesc") or ""
        ),
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

    client.post("/updateClass/v10", payload)
    return {
        "ok": True,
        "class_id": payload["classId"],
        "name": payload["className"],
        "days": new_days,
    }


def get_class(client: PlanbookClient, class_id: Any) -> Any:
    return client.post("/getClass", {"classId": intish(class_id)})


def delete_class(client: PlanbookClient, *, class_id: Any) -> dict[str, Any]:
    """Delete a class and every lesson in it. There is no undo."""
    client.post("/deleteClass", {"classId": intish(class_id)})
    return {"ok": True, "deleted_class_id": intish(class_id)}
