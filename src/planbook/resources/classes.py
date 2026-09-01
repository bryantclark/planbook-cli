"""Class resource operations."""

from __future__ import annotations

from collections.abc import Callable

from .. import projection
from ..client import PlanbookClient
from ..errors import PostconditionFailed, SchemaDrift, UsageError
from ..mutations import (
    Mutation,
    Request,
    commit,
    preview,
    require_intent,
    resolve_created,
)
from ..narrow import as_id, as_object, flag, records, string
from ..types import (
    ClassList,
    FormPayload,
    Id,
    JsonObject,
    JsonRecord,
    JsonValue,
    Result,
)
from ..widen import json_list
from ..wire import (
    DAY_ORDER,
    SCHEDULE_DAY_ORDER,
    build_schedule,
    edit_schedule,
    intish,
    yn,
)

#: Re-exported: the class projection lives with every other one.
normalize_class = projection.klass


def raw_classes(client: PlanbookClient) -> JsonValue:
    """The undecoded `/getClasses2` body. Backs `classes list --raw`."""
    return client.post("/getClasses2")


def list_classes(client: PlanbookClient) -> ClassList:
    """Classes with their weekly schedule."""
    checked = client.require(
        raw_classes(client), "classes", "currentYearId", where="getClasses2"
    )
    return ClassList(
        current_year_id=checked["currentYearId"],
        classes=[
            normalize_class(c)
            for c in records(checked["classes"], where="getClasses2.classes")
        ],
        lesson_banks=checked.get("lessonBanks"),
        district_lesson_banks=checked.get("districtLessonBanks"),
    )


def require_weekdays(days: list[str]) -> None:
    """Refuse a day name the schedule does not know.

    `class_payload` builds the week from `DAY_ORDER`, so an unrecognised name
    matches nothing: the class stores with every day off, teaches nothing, and
    accepts no lesson. It reports success the whole way.
    """
    unknown = sorted(day for day in days if day not in DAY_ORDER)
    if unknown:
        raise UsageError(
            f"Unknown weekday name(s): {', '.join(unknown)}. "
            f"Use {', '.join(DAY_ORDER)}.",
            remedy="On the command line, --days takes letters: M T W R F S U.",
        )


def require_taught(times: dict[str, tuple[str, str]] | None, days: list[str]) -> None:
    """Refuse a time for a day the class will not teach.

    Planbook blanks that slot, so the write would report success having stored
    nothing. The caller almost certainly forgot to name the day.
    """
    untaught = sorted(day for day in times or {} if day not in days)
    if untaught:
        raise UsageError(
            f"--time names {', '.join(untaught)}, which this class does not "
            "teach, so Planbook would discard it.",
            remedy="Pass --days including that day, or drop the --time.",
        )


def class_payload(
    *,
    name: str,
    start_date: str,
    end_date: str,
    days: list[str],
    color: str = "#7ED321",
    description: str = "",
    times: dict[str, tuple[str, str]] | None = None,
    lesson_layout_id: Id = 0,
) -> FormPayload:
    """Shared body for creating and updating a class.

    Booleans here are "Y"/"N". "true"/"false" is accepted and silently produces
    a class that teaches on no days at all.
    """
    payload: FormPayload = {
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
        "verifyShift": "false",  # "true" would validate and commit nothing
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
    lesson_layout_id: Id = 0,
    dry_run: bool = False,
) -> Result:
    require_weekdays(days)
    require_taught(times, days)
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
    mutation = Mutation(
        resource="class",
        operation="create",
        requests=[Request("/addClass", payload)],
    )
    if dry_run:
        return preview(mutation)
    assert client is not None  # only the dry_run branch runs without one

    # /addClass does not report the id it created, and two classes can share a
    # name, so diff the ids and narrow by what was written.
    def class_records() -> list[JsonObject]:
        body = client.require(
            client.post("/getClasses2"), "classes", where="getClasses2"
        )
        return records(body["classes"], where="getClasses2.classes")

    before = {str(c.get("cId")) for c in class_records()}
    result = commit(client, mutation)
    class_id = resolve_created(
        resource="class",
        before=before,
        after=class_records(),
        id_of=lambda c: c.get("cId"),
        matches=lambda c: (
            str(c.get("cN")) == str(name) and str(c.get("cSd")) == str(start_date)
        ),
        list_command="planbook classes list",
    )
    _require_schedule(
        client, as_id(class_id, where="addClass.id"), days=days, times=times
    )
    return {
        **result,
        "name": name,
        "days": json_list(days),
        "id": class_id,
    }


def _require_schedule(
    client: PlanbookClient,
    class_id: Id,
    *,
    days: list[str],
    times: dict[str, tuple[str, str]] | None,
) -> None:
    """Prove the new class teaches the days it was given.

    `/addClass` reports success and can still store a class that teaches
    nothing, and a class that teaches nothing has no slot to write a lesson
    into - so the failure surfaces later, as a lesson that will not save.
    """
    record = as_object(get_class(client, class_id), where="getClass")
    failed = [
        field
        for field, check in _schedule_checks(days, times).items()
        if not check(record)
    ]
    if failed:
        raise PostconditionFailed(
            f"The class was created (id {class_id}) but its "
            f"{', '.join(failed)} did not store, so it teaches nothing and no "
            "lesson can be written to it.",
            details={"id": class_id, "unstored": failed},
            remedy=(
                "Do NOT retry - the class exists. Set the schedule in "
                "Planbook's own UI, or delete it with `planbook classes "
                "delete --class-id <id> --yes`."
            ),
        )


def update_class(
    client: PlanbookClient,
    *,
    class_id: Id,
    name: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    days: list[str] | None = None,
    color: str | None = None,
    description: str | None = None,
    times: dict[str, tuple[str, str]] | None = None,
    dry_run: bool = False,
) -> Result:
    """Update a class, changing only what you pass.

    The endpoint replaces the whole record, so this reads the class first and
    edits that. `scheduleChange=true` is required or the new schedule is
    discarded while the rest of the update succeeds.
    """
    current = as_object(get_class(client, class_id), where=f"getClass({class_id})")
    if "className" not in current:
        raise SchemaDrift(
            f"getClass({class_id}) did not return a class record. "
            "Cannot update without reading the current values first."
        )
    schedule_rows = records(
        current.get("classSchedule") or [], where="getClass.classSchedule"
    )
    if not schedule_rows:
        raise SchemaDrift(
            f"getClass({class_id}) returned no classSchedule. Updating without "
            "it would erase the class's teaching days."
        )

    # The schedule rows are authoritative for teaching days; the scalar
    # <day>Teach fields are a flattened view of the latest row.
    latest = schedule_rows[-1]
    current_days = [
        day
        for n, day in enumerate(SCHEDULE_DAY_ORDER, start=1)
        if flag(latest.get(f"day{n}Teach"))
    ]
    new_days = days if days is not None else current_days
    start = start_date or string(current, "classStartDate")

    payload: FormPayload = {
        "classId": intish(class_id),
        "className": name if name is not None else string(current, "className"),
        "classStartDate": start,
        "classEndDate": end_date or string(current, "classEndDate"),
        "color": color if color is not None else string(current, "color", "#7ED321"),
        "classDesc": (
            description if description is not None else string(current, "classDesc")
        ),
        "titleColor": string(current, "titleColor", "#000000"),
        "titleSize": string(current, "titleSize", "12"),
        "titleFont": string(current, "titleFont", "Arial"),
        "classLabelBold": yn(flag(current.get("classLabelBold"))),
        "classLabelItalic": yn(flag(current.get("classLabelItalic"))),
        "classLabelUnderline": yn(flag(current.get("classLabelUnderline"))),
        "noStudents": yn(flag(current.get("noStudents"))),
        "useSchoolStart": yn(flag(current.get("useSchoolStart"))),
        "useSchoolEnd": yn(flag(current.get("useSchoolEnd"))),
        "lessonLayoutId": intish(current.get("lessonLayoutId")),
        "source": string(current, "source"),
        "sourceId": intish(current.get("sourceId")),
        "collaborateType": intish(current.get("collaborateType")),
        "collaborateSubjectId": intish(current.get("collaborateSubjectId")),
        "collaborateKey": string(current, "collaborateKey"),
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

    # Keyed by the field `getClass` answers with, so the read-back checks
    # exactly what this call changed.
    require_weekdays(new_days)
    require_taught(times, new_days)
    named = {
        public: (field, str(payload.get(field, "")))
        for public, field, value in (
            ("name", "className", name),
            ("start_date", "classStartDate", start_date),
            ("end_date", "classEndDate", end_date),
            ("color", "color", color),
            ("description", "classDesc", description),
        )
        if value is not None
    }
    mutation = Mutation(
        resource="class",
        operation="update",
        requests=[Request("/updateClass/v10", payload)],
        before=normalize_class_record(current, class_id),
        named=named,
        # The schedule comes back as `classSchedule`, a list of rotation rows,
        # so it is checked by predicate rather than by flat comparison.
        checks=_schedule_checks(new_days if days is not None else None, times),
    )
    if dry_run:
        return preview(mutation)

    result = commit(
        client,
        mutation,
        read=lambda: as_object(get_class(client, class_id), where="getClass"),
    )
    return {
        **result,
        "id": str(payload["classId"]),
        "name": str(payload["className"]),
        "days": json_list(new_days),
    }


def _schedule_checks(
    days: list[str] | None, times: dict[str, tuple[str, str]] | None
) -> dict[str, Callable[[JsonRecord], bool]]:
    """Predicates proving a schedule change took.

    `scheduleChange=true` is easy to lose: the rest of the update lands and the
    new teaching days are quietly discarded.
    """
    checks: dict[str, Callable[[JsonRecord], bool]] = {}
    if days is not None:
        # Compared as sets: `--days WM` is the same schedule as `--days MW`.
        checks["days"] = lambda record: set(_taught(record)) == set(days)
    if times:
        checks["times"] = lambda record: all(
            _slot(record, day) == window for day, window in times.items()
        )
    return checks


def _latest_row(record: JsonRecord) -> JsonObject | None:
    """The current schedule row. Earlier rows are a mid-year change's history."""
    schedule = record.get("classSchedule")
    if not isinstance(schedule, list):
        return None
    rows = records(schedule, where="getClass.classSchedule")
    return rows[-1] if rows else None


def _taught(record: JsonRecord) -> list[str]:
    """The weekdays the saved schedule teaches on."""
    row = _latest_row(record)
    if row is None:
        return []
    return [
        day
        for n, day in enumerate(SCHEDULE_DAY_ORDER, start=1)
        if flag(row.get(f"day{n}Teach"))
    ]


def _slot(record: JsonRecord, day: str) -> tuple[str, str]:
    """The saved start and end time for one weekday."""
    row = _latest_row(record)
    if row is None or day not in SCHEDULE_DAY_ORDER:
        return ("", "")
    n = SCHEDULE_DAY_ORDER.index(day) + 1
    return (
        str(row.get(f"day{n}StartTime") or ""),
        str(row.get(f"day{n}EndTime") or ""),
    )


def normalize_class_record(current: JsonObject, class_id: Id) -> Result:
    """`getClass` speaks readable keys already; project the few that matter."""
    return {
        "id": intish(class_id),
        "name": current.get("className"),
        "start_date": current.get("classStartDate"),
        "end_date": current.get("classEndDate"),
        "color": current.get("color"),
        "description": current.get("classDesc"),
    }


def get_class(client: PlanbookClient, class_id: Id) -> JsonValue:
    return client.post("/getClass", {"classId": intish(class_id)})


def delete_class(
    client: PlanbookClient,
    *,
    class_id: Id,
    dry_run: bool = False,
    confirmed: bool = False,
) -> Result:
    """Delete a class and every lesson in it. There is no undo."""
    from .lessons import lessons_between

    current = as_object(get_class(client, class_id), where=f"getClass({class_id})")
    if "className" not in current:
        raise SchemaDrift(
            f"getClass({class_id}) did not return a class record. Refusing to "
            "delete a class this tool cannot describe."
        )
    # A class always takes its lessons with it, so `--yes` is always required.
    # Counting them costs a request, so only count for a preview or a refusal.
    cascade: Result = {"lessons": "every lesson in this class"}
    if dry_run or not confirmed:
        cascade = {
            "lessons": sum(
                str(lesson.get("class_id")) == str(intish(class_id))
                for lesson in lessons_between(
                    client,
                    start=string(current, "classStartDate"),
                    end=string(current, "classEndDate"),
                )
            )
        }
    mutation = Mutation(
        resource="class",
        operation="delete",
        requests=[Request("/deleteClass", {"classId": intish(class_id)})],
        before=normalize_class_record(current, class_id),
        cascade=cascade,
    )
    if dry_run:
        return preview(mutation)
    require_intent(mutation, confirmed=confirmed)
    return commit(
        client,
        mutation,
        verify=lambda: _class_or_none(client, class_id),
        result={"deleted_class_id": intish(class_id)},
    )


def _class_or_none(client: PlanbookClient, class_id: Id) -> JsonObject | None:
    """The class, or None once it is gone.

    Asked of the list, not `/getClass`: a deleted class keeps answering there
    with its whole record, so reading it back that way called every successful
    delete a PostconditionFailed. The list is what forgets it.
    """
    wanted = str(intish(class_id))
    body = client.require(client.post("/getClasses2"), "classes", where="getClasses2")
    for record in records(body["classes"], where="getClasses2.classes"):
        if str(record.get("cId")) == wanted:
            return record
    return None
