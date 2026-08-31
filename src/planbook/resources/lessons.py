"""Lesson resource operations."""

from __future__ import annotations

import contextlib
import datetime
import json
from collections.abc import Callable, Iterator

from ..client import PlanbookClient
from ..errors import PostconditionFailed, SchemaDrift, UsageError
from ..mutations import (
    Mutation,
    Request,
    commit,
    preview,
    require_intent,
    send,
)
from ..narrow import as_id, as_object, flag, records
from ..types import (
    AttachmentLink,
    FormPayload,
    Id,
    JsonObject,
    JsonRecord,
    JsonValue,
    LessonSection,
    Result,
    WeekDay,
    WeekLesson,
)
from ..widen import json_list
from ..wire import intish, parse_date, yn
from .misc import list_assignments, settings


def delete_lesson(
    client: PlanbookClient,
    *,
    class_id: Id,
    date: str,
    dry_run: bool = False,
) -> Result:
    date = parse_date(date)
    payload = {"classId": intish(class_id), "customDate": date, "userMode": "T"}
    mutation = Mutation(
        resource="lesson",
        operation="delete",
        requests=[Request("/deleteLesson", payload)],
    )
    if dry_run:
        existing = find_lesson(client, class_id=class_id, date=date)
        mutation.before = (
            {
                "class_id": existing.get("classId"),
                "date": date,
                "title": existing.get("lessonTitle"),
                "lesson_id": existing.get("lessonId"),
            }
            if existing
            else None
        )
        return preview(mutation)
    require_intent(mutation, confirmed=False)
    result = commit(
        client,
        mutation,
        verify=lambda: find_lesson(client, class_id=class_id, date=date),
    )
    return {**result, "class_id": payload["classId"], "date": date}


def no_school_dates(client: PlanbookClient) -> set[str]:
    """Dates the calendar marks as no-school.

    Advisory, so every failure is swallowed: a warning must never stop the
    write it annotates.
    """
    dates: set[str] = set()
    try:
        from .events import wire_events

        for event in wire_events(client, limit=1000):
            if flag(event.get("noSchool")):
                for key in ("eventDate", "eventCurrentDate"):
                    if event.get(key):
                        dates.add(str(event[key]))
    except Exception:
        return set()
    return dates


def iter_days(body: JsonValue) -> Iterator[JsonObject]:
    """Yield each day in a getLessonsEvents response.

    A lesson carries no date of its own; the date comes from its day. `objects`
    holds a placeholder for every class, saved lesson or not.
    """
    envelope = as_object(body, where="getLessonsEvents")
    if "days" not in envelope:
        raise SchemaDrift("getLessonsEvents returned no `days` list.")
    for day in records(envelope["days"], where="getLessonsEvents.days"):
        if day.get("date"):
            yield day


def read_week(
    client: PlanbookClient, *, monday: str, weeks: int = 1, saved_only: bool = True
) -> list[WeekDay]:
    """Lessons for a week, grouped by date."""
    body = get_week(client, monday=monday, weeks=weeks)
    out: list[WeekDay] = []
    for day in iter_days(body):
        slots = records(day.get("objects") or [], where="getLessonsEvents.objects")
        out.append(
            WeekDay(
                date=day["date"],
                day_of_week=day.get("dayOfWeek"),
                lessons=[
                    _week_lesson(obj, day["date"])
                    for obj in slots
                    if (obj.get("lessonId") or not saved_only) and obj.get("classId")
                ],
            )
        )
    return out


def _week_lesson(obj: JsonObject, date: object) -> WeekLesson:
    """One class slot in a week view, projected."""
    return WeekLesson(
        date=date,
        class_id=obj.get("classId"),
        class_name=obj.get("className"),
        lesson_id=obj.get("lessonId"),
        title=obj.get("lessonTitle"),
        start=obj.get("startTime"),
        end=obj.get("endTime"),
        text=obj.get("lessonText"),
        homework=obj.get("homeworkText"),
        notes=obj.get("notesText"),
        standards=[
            st.get("id")
            for st in records(obj.get("standards") or [], where="lesson.standards")
        ],
        assignments=[
            a.get("assignmentTitle")
            for a in records(obj.get("assignments") or [], where="lesson.assignments")
        ],
        attachments=[
            a.get("filename")
            for a in records(obj.get("attachments") or [], where="lesson.attachments")
        ],
    )


def find_lesson(
    client: PlanbookClient, *, class_id: Id, date: str
) -> JsonObject | None:
    """The saved lesson for one class on one date, or None."""
    # Zero-padded: the compare below is an exact string match. See parse_date.
    date = parse_date(date)
    body = get_week(client, monday=date, weeks=1)
    wanted = str(intish(class_id))
    for day in iter_days(body):
        if day["date"] != date:
            continue
        for obj in records(day.get("objects") or [], where="getLessonsEvents.objects"):
            if str(obj.get("classId")) == wanted and obj.get("lessonId"):
                return obj
    return None


def _html(value: JsonValue) -> str:
    """Text fields come back as strings or None; normalise for re-sending."""
    return "" if value is None else str(value)


def lesson_payload(
    *,
    class_id: Id,
    date: str,
    title: str | None = None,
    text: str | None = None,
    homework: str | None = None,
    notes: str | None = None,
    unit_id: Id | None = None,
    sections: dict[int, str] | None = None,
    standards: list[str] | None = None,
    assignments: list[Id] | None = None,
    attach: list[AttachmentLink] | None = None,
) -> tuple[FormPayload, list[str]]:
    """Build the form payload and the list of fields it updates.

    Pure, which is what lets --dry-run work offline.
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
    if not updated and unit_id is None:
        raise UsageError(
            "Nothing to write. Pass at least one of --title, --text, "
            "--homework, --notes, --unit-id, --section, --standard, "
            "--assignment, --attach."
        )

    payload: FormPayload = {
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
        # Repeated triples, one per file. The lesson stores the signed URL
        # itself, so the link outlives the resource list.
        payload["attachmentNames"] = [a["name"] for a in attach] or [""]
        payload["attachmentURL"] = [a["url"] for a in attach] or [""]
        payload["attachmentPrivate"] = ["N" for _ in attach] or [""]

    if standards is not None:
        # Repeated form fields, not a comma list: a comma-joined value is
        # accepted and clears the set instead. Sending ids replaces the set.
        payload["standardDBIds"] = [str(s) for s in standards] or [""]
    if assignments is not None:
        # Sending "[]" detaches whatever the lesson already had, so this is
        # sent only when the caller named assignments.
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


def _attachment_checks(
    standards: list[str] | None,
    assignments: list[Id] | None,
    attach: list[AttachmentLink] | None,
) -> dict[str, Callable[[JsonRecord], bool]]:
    """Predicates proving the attached sets took.

    Attachments come back by name, so those compare exactly. Standards and
    assignments come back keyed differently from the ids the write sends -
    `standards[].id` is the human "3.NBT.A.1", not the `dbId` that attaches
    one - so those compare by count, which still catches the failure that
    happens: the server dropping the set entirely.
    """
    checks: dict[str, Callable[[JsonRecord], bool]] = {}
    if standards is not None:
        checks["standards"] = lambda record: (
            len(_listed(record, "standards")) == len(standards)
        )
    if assignments is not None:
        checks["assignments"] = lambda record: (
            len(_listed(record, "assignments")) == len(assignments)
        )
    if attach is not None:
        checks["attachments"] = lambda record: (
            {str(a.get("filename")) for a in _listed(record, "attachments")}
            == {a["name"] for a in attach}
        )
    return checks


def _listed(record: JsonRecord, key: str) -> list[JsonObject]:
    value = record.get(key)
    return records(value, where=f"lesson.{key}") if isinstance(value, list) else []


def lesson_mutation(
    payload: FormPayload,
    *,
    named: dict[str, tuple[str, str]] | None = None,
    checks: dict[str, Callable[[JsonRecord], bool]] | None = None,
    create_first: bool = False,
    before: JsonRecord | None = None,
    effects: Result | None = None,
) -> Mutation:
    """Describe a lesson write.

    `create_first` covers the two-write case: standards, assignments and
    attachments only stick to a lesson that already exists, so a brand-new
    date is created empty and then written again.
    """
    requests = []
    if create_first:
        requests.append(
            Request("/updateLesson", dict(payload, standardDBIds="", schoolWorks="[]"))
        )
    requests.append(Request("/updateLesson", payload))
    return Mutation(
        resource="lesson",
        operation="update",
        requests=requests,
        before=before,
        named=named or {},
        checks=checks or {},
        effects=effects or {},
    )


def _reject_duplicate_sections(
    *,
    text: str | None,
    homework: str | None,
    notes: str | None,
    sections: dict[int, str] | None,
) -> None:
    """Refuse a write that names one lesson section twice.

    Sections 1-3 are the same fields as --text, --homework and --notes. Only
    one value can be stored, so accepting both would report a field as written
    that the other flag overwrote.
    """
    named = {1: ("--text", text), 2: ("--homework", homework), 3: ("--notes", notes)}
    clashes = [
        f"--section {index} and {flag_name}"
        for index, (flag_name, value) in named.items()
        if value is not None and index in (sections or {})
    ]
    if clashes:
        raise UsageError(
            " ".join(f"{clash} write the same lesson section." for clash in clashes),
            remedy="Drop either the --section flag or the field flag it repeats.",
        )


def set_lesson(
    client: PlanbookClient,
    *,
    class_id: Id,
    date: str,
    title: str | None = None,
    text: str | None = None,
    homework: str | None = None,
    notes: str | None = None,
    unit_id: Id | None = None,
    sections: dict[int, str] | None = None,
    standards: list[str] | None = None,
    assignments: list[Id] | None = None,
    attach: list[AttachmentLink] | None = None,
    attach_pending: list[str] | None = None,
    dry_run: bool = False,
) -> Result:
    """Create or update the lesson for one class on one date.

    `/updateLesson` is keyed by class and date, not lesson id, so this is an
    upsert: writing the same date twice edits in place.

    `dry_run` still reads the current lesson. It has to: the carried-over text
    is most of the payload, and a preview built without it would show this
    write blanking fields that the real one preserves.
    """
    # `updatedFields` is not a mask: any text field sent empty is written
    # empty. So every write is read-modify-write.
    if all(
        value is None
        for value in (
            title,
            text,
            homework,
            notes,
            unit_id,
            sections,
            standards,
            assignments,
            attach,
        )
    ):
        # Checked before the read: once carry-over fills these from the saved
        # lesson, `lesson_payload`'s own guard can no longer tell "write
        # nothing" from "rewrite the lesson with itself".
        raise UsageError(
            "Nothing to write. Pass at least one of --title, --text, "
            "--homework, --notes, --unit-id, --section, --standard, "
            "--assignment, --attach."
        )
    _reject_duplicate_sections(
        text=text, homework=homework, notes=notes, sections=sections
    )
    # Snapshot what the caller named before carry-over fills the rest in:
    # `updated` ends up listing every field being sent, which on an upsert is
    # nearly all of them, and a field carried over cannot prove anything.
    named = [
        (name, field)
        for name, field, value in (
            ("title", "lessonTitle", title),
            ("text", "lessonText", text),
            ("homework", "homeworkText", homework),
            ("notes", "notesText", notes),
            ("unit_id", "unitId", unit_id),
        )
        if value is not None
        # `--unit-id 0` clears the unit, and an unfiled lesson comes back with
        # no unitId at all, so there is nothing to compare it against.
        and not (field == "unitId" and str(value) in ("0", ""))
    ] + [(f"section{index}", SECTION_FIELDS[index]) for index in sections or {}]
    existing = find_lesson(client, class_id=class_id, date=date)
    unit_only = [name for name, _ in named] == ["unit_id"] and (
        standards is None and assignments is None and attach is None
    )
    if existing is None and unit_only:
        # Carry-over is what makes a unit move a complete payload. Without a
        # saved lesson there is nothing to move, and the write would file an
        # empty lesson under the unit.
        raise UsageError(
            f"There is no lesson for class {intish(class_id)} on {date} to "
            "file under a unit. Write the lesson first, or pass --title or "
            "--text alongside --unit-id."
        )
    carry: FormPayload = {}
    before: JsonObject | None = None
    if existing:
        before = {
            "class_id": existing.get("classId"),
            "date": date,
            "lesson_id": existing.get("lessonId"),
            "title": existing.get("lessonTitle"),
        }
        title = title if title is not None else _html(existing.get("lessonTitle"))
        text = text if text is not None else _html(existing.get("lessonText"))
        homework = (
            homework if homework is not None else _html(existing.get("homeworkText"))
        )
        notes = notes if notes is not None else _html(existing.get("notesText"))
        if unit_id is None:
            unit_id = (
                as_id(existing["unitId"], where="lesson.unitId")
                if existing.get("unitId")
                else None
            )
        carried = {
            index: _html(existing.get(field))
            for index, field in SECTION_FIELDS.items()
            if index >= 4 and existing.get(field)
        }
        if carried:
            sections = {**carried, **(sections or {})}
        # Flags the payload would otherwise reset to their defaults.
        carry = {
            "lessonLock": yn(flag(existing.get("lessonLock"))),
            "extraLesson": intish(existing.get("extraLesson")),
            "linkedLessonId": intish(existing.get("linkedLessonId")),
            "isEditingALinkedLesson": yn(flag(existing.get("isEditingALinkedLesson"))),
        }

    payload, _updated = lesson_payload(
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
    payload.update(carry)

    if assignments:
        # Attaching an assignment from another class is accepted and does
        # nothing.
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

    attaching = standards is not None or assignments is not None or attach is not None
    # Standards, assignments and attachments stick only to a lesson that
    # already exists; on a new date the id is 0 and the server drops them.
    create_first = attaching and existing is None
    if attaching and existing and existing.get("lessonId"):
        payload["lessonId"] = str(existing["lessonId"])

    effects: Result = {}
    if standards is not None:
        effects["standards"] = json_list(standards)
    if assignments is not None:
        effects["assignments"] = [str(a) for a in assignments]
    if attach is not None:
        effects["attachments"] = [a["name"] for a in attach]

    if attach_pending:
        # A dry run uploads nothing, so name what a real run would attach.
        effects["attachments_pending"] = json_list(attach_pending)
    mutation = lesson_mutation(
        payload,
        named={name: (field, str(payload[field])) for name, field in named},
        checks=_attachment_checks(standards, assignments, attach),
        create_first=create_first,
        before=before,
        effects=effects,
    )
    if dry_run:
        return preview(mutation)
    if create_first:
        # The new row's id is only knowable after the first write, so the
        # second request's lessonId is filled in between the two.
        _send_and_link(client, mutation, class_id=class_id, date=date)
    else:
        # Existence proves nothing on an upsert: an untouched lesson comes
        # back looking exactly like a written one, so `commit` compares the
        # fields this call named.
        commit(
            client,
            mutation,
            read=lambda: find_lesson(client, class_id=class_id, date=date),
        )
    result: Result = {
        "ok": True,
        "class_id": str(payload["classId"]),
        "date": date,
        "updated_fields": json_list(mutation.updated_fields),
        **({"effects": effects} if effects else {}),
    }
    return result


def _send_and_link(
    client: PlanbookClient, mutation: Mutation, *, class_id: Id, date: str
) -> None:
    """Run the create-then-attach pair, carrying the new lesson id across."""
    send(client, mutation.requests[0])
    created = find_lesson(client, class_id=class_id, date=date)
    if created is None:
        raise PostconditionFailed(
            f"Creating the lesson for class {intish(class_id)} on {date} "
            "reported success but stored nothing, so there is nothing to "
            "attach standards or assignments to.",
            details={"class_id": intish(class_id), "date": date},
        )
    payload = dict(mutation.requests[1].payload)
    payload["lessonId"] = str(created.get("lessonId") or "0")
    mutation.requests[1] = Request("/updateLesson", payload)
    commit(
        client,
        Mutation(
            resource="lesson",
            operation="update",
            requests=[mutation.requests[1]],
            # The row already exists - request one created it - so existence
            # proves nothing here either.
            named=mutation.named,
            checks=mutation.checks,
        ),
        read=lambda: find_lesson(client, class_id=class_id, date=date),
    )


def get_week(client: PlanbookClient, *, monday: str, weeks: int = 1) -> JsonValue:
    """The undecoded `/getLessonsEvents` body for a week starting on a Monday.

    Backs `lessons week --raw`; `read_week` is the decoded form.
    """
    return client.post(
        "/getLessonsEvents",
        {"monday": monday, "userMode": "T", "fetchWeekSize": str(weeks)},
    )


# Tabs 4-6 are named and enabled per lesson layout, and read "Not Used" until
# someone configures them.
SECTION_FIELDS = {
    1: "lessonText",
    2: "homeworkText",
    3: "notesText",
    4: "tab4Text",
    5: "tab5Text",
    6: "tab6Text",
}
DEFAULT_SECTION_LABELS = {1: "Lesson", 2: "Homework", 3: "Notes"}


def lesson_sections(client: PlanbookClient) -> list[LessonSection]:
    """The six lesson sections with their current labels and enabled state."""
    conf = settings(client)
    if not isinstance(conf, dict):
        raise SchemaDrift("getSettings did not return an object.")
    out: list[LessonSection] = []
    for index, field in SECTION_FIELDS.items():
        label = conf.get(f"tab{index}Label") or DEFAULT_SECTION_LABELS.get(index)
        raw_enabled = conf.get(f"tab{index}Enabled")
        enabled = True if raw_enabled in (None, "") else flag(raw_enabled)
        out.append(
            LessonSection(
                section=index,
                label=str(label or f"Tab {index}"),
                enabled=enabled if index > 3 else True,
                field=field,
            )
        )
    return out


def resolve_section(sections: list[LessonSection], key: str) -> int:
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
) -> list[WeekLesson]:
    """Saved lessons falling on or between two dates."""
    start, end = parse_date(start), parse_date(end)
    weeks = 1
    with contextlib.suppress(ValueError):
        weeks = max(1, (_as_date(end) - _as_date(start)).days // 7 + 2)
    found: list[WeekLesson] = []
    for day in read_week(client, monday=start, weeks=weeks):
        # Compare dates, not MM/DD/YYYY strings: "01/05/2027" sorts lexically
        # before "12/22/2026".
        try:
            in_range = _as_date(start) <= _as_date(str(day["date"])) <= _as_date(end)
        except ValueError:
            in_range = day["date"] == start
        if in_range:
            found.extend(day["lessons"])
    return found


def _as_date(value: str) -> datetime.date:
    month, day, year = (int(part) for part in value.split("/"))
    return datetime.date(year, month, day)
