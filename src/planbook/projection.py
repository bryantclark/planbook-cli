"""One readable projection per mapped entity.

Planbook's wire format abbreviates and is inconsistent about identity: classes
answer with `cId`, units with `unitId`, to-dos with `toDoId`, events with
`eventId`, students with `studentId`.

Everything that leaves this CLI is projected here, so `id` means the same thing
on every resource. `--raw` returns the untouched wire body.
"""

from __future__ import annotations

from .narrow import as_object, flag, records, text
from .types import (
    Class,
    DaySchedule,
    Event,
    JsonObject,
    JsonValue,
    Lesson,
    Student,
    Template,
    Todo,
    Unit,
)
from .wire import DAY_PREFIXES, PRIORITY_NAMES, UNIT_SECTION_FIELDS


def _obj(raw: JsonValue, what: str) -> JsonObject:
    return as_object(raw, where=f"a {what} record")


def klass(raw: JsonValue) -> Class:
    """One class, readable. Named `klass` because `class` is a keyword."""
    record = _obj(raw, "class")
    schedule = {}
    for day, prefix in DAY_PREFIXES.items():
        schedule[day] = DaySchedule(
            teaches=flag(record.get(f"{prefix}T")),
            start=record.get(f"{prefix}St"),
            end=record.get(f"{prefix}Et"),
        )
    return Class(
        id=record.get("cId"),
        name=record.get("cN"),
        start_date=record.get("cSd"),
        end_date=record.get("cEd"),
        color=record.get("cC"),
        year_id=record.get("cYId"),
        description=record.get("classDesc"),
        lesson_layout_id=record.get("lessonLayoutId"),
        teacher_id=record.get("teacherId"),
        district_id=record.get("districtId"),
        units=record.get("units"),
        schedule=schedule,
    )


def unit(raw: JsonValue) -> Unit:
    """One unit, readable. `sections` holds only the sections that have text."""
    record = _obj(raw, "unit")
    sections = {
        index: str(record[field])
        for index, field in UNIT_SECTION_FIELDS.items()
        if record.get(field)
    }
    return Unit(
        id=record.get("unitId"),
        class_id=record.get("subjectId"),
        number=record.get("unitNum"),
        title=record.get("unitTitle"),
        description=text(record, "unitDesc"),
        start_date=text(record, "unitStart"),
        end_date=text(record, "unitEnd"),
        sections=sections,
    )


def todo(raw: JsonValue) -> Todo:
    record = _obj(raw, "to-do")
    return Todo(
        id=record.get("toDoId"),
        text=record.get("toDoText"),
        start_date=text(record, "startDate"),
        due_date=text(record, "dueDate"),
        priority=PRIORITY_NAMES.get(
            str(record.get("priority")), str(record.get("priority") or "")
        )
        or None,
        done=flag(record.get("done")),
        repeats=text(record, "repeats"),
        class_id=record.get("subjectId") or record.get("classId"),
    )


def event(raw: JsonValue) -> Event:
    record = _obj(raw, "event")
    return Event(
        id=record.get("eventId") or record.get("id"),
        title=record.get("eventTitle"),
        date=text(record, "eventDate"),
        end_date=text(record, "endDate", "eventDate"),
        current_date=text(record, "eventCurrentDate"),
        text=text(record, "eventText"),
        start_time=text(record, "eventStartTime"),
        end_time=text(record, "eventEndTime"),
        repeats=text(record, "repeats"),
        no_school=flag(record.get("noSchool")),
        private=flag(record.get("privateFlag")),
        school_id=record.get("schoolId"),
        district_id=record.get("districtId"),
    )


def template(raw: JsonValue) -> Template:
    record = _obj(raw, "template")
    return Template(
        id=record.get("templateId") or record.get("id"),
        name=text(record, "templateName", "name"),
        class_id=record.get("subjectId") or record.get("classId"),
    )


def student(raw: JsonValue) -> Student:
    """One student from the per-class endpoint."""
    record = _obj(raw, "student")
    return Student(
        id=record.get("studentId") or record.get("id"),
        first_name=record.get("firstName"),
        last_name=record.get("lastName"),
        code=record.get("code"),
        email=record.get("emailAddress"),
        gender=record.get("gender"),
    )


def lesson(raw: JsonValue, *, date: object = None) -> Lesson:
    """A saved lesson, keyed the way `lessons set` names its flags.

    A lesson carries no date on the wire - the date belongs to the day it was
    read from - so the caller supplies the one it asked for.
    """
    record = _obj(raw, "lesson")
    return Lesson(
        class_id=record.get("classId"),
        date=date if date is not None else record.get("date"),
        lesson_id=record.get("lessonId"),
        title=record.get("lessonTitle"),
        text=record.get("lessonText"),
        homework=record.get("homeworkText"),
        notes=record.get("notesText"),
        section4=record.get("tab4Text"),
        section5=record.get("tab5Text"),
        section6=record.get("tab6Text"),
        unit_id=record.get("unitId"),
        unit_title=record.get("unitTitle"),
        standards=[
            st.get("id")
            for st in records(record.get("standards") or [], where="lesson.standards")
        ],
        assignments=[
            a.get("assignmentTitle")
            for a in records(
                record.get("assignments") or [], where="lesson.assignments"
            )
        ],
        attachments=[
            at.get("fileName")
            for at in records(
                record.get("attachments") or [], where="lesson.attachments"
            )
        ],
    )
