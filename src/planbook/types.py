"""Types shared across the CLI: wire-facing aliases and the projected records."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal, TypeAlias, TypedDict

#: A record id. Ints come off the wire, strings come off the command line.
Id: TypeAlias = int | str

#: One form field's value. Lists are the repeated fields the API requires.
FormValue: TypeAlias = str | list[str]

#: A form-encoded request body.
FormPayload: TypeAlias = dict[str, FormValue]

#: A form body being read rather than built. Covariant, so a `dict[str, str]`
#: from a payload builder is accepted without copying it.
FormBody: TypeAlias = Mapping[str, FormValue]

#: A parsed JSON body. Recursive, so narrowing is forced before indexing.
JsonValue: TypeAlias = (
    "str | int | float | bool | list[JsonValue] | dict[str, JsonValue] | None"
)

#: A JSON object, once narrowed.
JsonObject: TypeAlias = dict[str, "JsonValue"]

#: Any record being read or serialised. `object` rather than `JsonValue`
#: because that is the only value type a TypedDict is assignable to.
JsonRecord: TypeAlias = Mapping[str, object]

#: A result this CLI builds and prints, as opposed to one it parsed.
Result: TypeAlias = dict[str, object]

#: How a request is sent. Mirrors the three shapes PlanbookClient speaks.
Method: TypeAlias = Literal["GET", "POST", "POST-json"]


class DaySchedule(TypedDict):
    """One weekday of a class's timetable."""

    teaches: bool
    start: object
    end: object


class Class(TypedDict):
    id: object
    name: object
    start_date: object
    end_date: object
    color: object
    year_id: object
    description: object
    lesson_layout_id: object
    teacher_id: object
    district_id: object
    units: object
    schedule: dict[str, DaySchedule]


class ClassList(TypedDict):
    """What `classes list` returns."""

    current_year_id: object
    classes: list[Class]
    lesson_banks: object
    district_lesson_banks: object


class Unit(TypedDict):
    id: object
    class_id: object
    number: object
    title: object
    description: str | None
    start_date: str | None
    end_date: str | None
    sections: dict[int, str]


class Todo(TypedDict):
    id: object
    text: object
    start_date: str | None
    due_date: str | None
    priority: str | None
    done: bool
    repeats: str | None
    class_id: object


class Event(TypedDict):
    id: object
    title: object
    date: str | None
    end_date: str | None
    current_date: str | None
    text: str | None
    start_time: str | None
    end_time: str | None
    repeats: str | None
    no_school: bool
    private: bool
    school_id: object
    district_id: object


class Template(TypedDict):
    id: object
    name: str | None
    class_id: object


class Student(TypedDict, total=False):
    """A student, projected. The account-wide endpoint gives a name only, so
    every key but `id` is optional."""

    id: object
    name: object
    first_name: object
    last_name: object
    code: object
    email: object
    gender: object


class Standard(TypedDict):
    """A standard. `db_id` is what attaches it to a lesson, not `id`."""

    db_id: object
    id: object
    description: object
    subject: object
    category: object


class Attachment(TypedDict):
    name: object
    url: object
    size: object


class AttachmentLink(TypedDict):
    """The name and signed URL a lesson stores for an attachment."""

    name: str
    url: str


class LessonSection(TypedDict):
    """One of the six lesson sections, with its label from the layout."""

    section: int
    label: str
    enabled: bool
    field: str


class WeekLesson(TypedDict):
    """One saved lesson in a week view."""

    date: object
    class_id: object
    class_name: object
    lesson_id: object
    title: object
    start: object
    end: object
    text: object
    homework: object
    notes: object
    standards: list[object]
    assignments: list[object]
    attachments: list[object]


class WeekDay(TypedDict):
    """One day of a week view."""

    date: object
    day_of_week: object
    lessons: list[WeekLesson]


class BulkItem(TypedDict, total=False):
    """One entry from a `lessons bulk` file, already checked by the validator."""

    class_id: Id
    date: str
    title: str
    text: str
    homework: str
    notes: str
    unit_id: Id
    sections: dict[int, str]
