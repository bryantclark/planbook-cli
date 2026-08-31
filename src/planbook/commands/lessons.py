"""Lesson command callbacks."""

from __future__ import annotations

import argparse
import functools
import json
import sys
from collections.abc import Callable
from pathlib import Path

from .. import projection
from ..cli_support import (
    STDIN,
    client_from,
    emit,
    read_stdin,
    resolve_stdin,
    teacher_id_from,
)
from ..client import PlanbookClient
from ..errors import PlanbookError, UsageError
from ..journal import Journal, key_for, open_journal, payload_hash
from ..narrow import as_id
from ..resources.lessons import (
    delete_lesson,
    find_lesson,
    get_week,
    lesson_payload,
    lesson_sections,
    no_school_dates,
    read_week,
    resolve_section,
    set_lesson,
)
from ..resources.misc import resolve_attachments
from ..types import (
    AttachmentLink,
    BulkItem,
    Id,
    JsonObject,
    JsonValue,
    LessonSection,
    Result,
)
from ..wire import parse_date


def _sections_from(
    args: argparse.Namespace, client: PlanbookClient | None
) -> dict[int, str] | None:
    """Resolve --section SPEC values to section indexes.

    Labels come from the account's lesson layout, so a numbered section makes
    no call.
    """
    if not args.section:
        return None
    resolved: dict[int, str] = {}
    known: list[LessonSection] | None = None
    for spec in args.section:
        key, sep, value = spec.partition("=")
        if not sep:
            raise UsageError(
                f"--section {spec!r} needs KEY=TEXT, e.g. 4=... or Homework=..."
            )
        if not key.strip().isdigit() and known is None:
            known = lesson_sections(client or client_from(args))
        if value == STDIN:
            value = read_stdin()
        resolved[resolve_section(known or [], key)] = value
    return resolved


def cmd_lessons_sections(args: argparse.Namespace) -> None:
    emit(lesson_sections(client_from(args)))


def _attachments_from(
    args: argparse.Namespace, client: PlanbookClient | None
) -> list[AttachmentLink] | None:
    """Resolve --attach values: a local path is uploaded, a name is looked up."""
    if not args.attach:
        return None
    if client is None:
        raise UsageError("--attach needs a network connection; drop --dry-run.")
    return resolve_attachments(
        client, list(args.attach), teacher_id=teacher_id_from(args)
    )


def cmd_lessons_set(args: argparse.Namespace) -> None:
    resolve_stdin(args, "text", "homework", "notes", "title")
    client = client_from(args)
    if not args.dry_run and args.date in no_school_dates(client):
        print(f"warning: {args.date} is marked as a no-school day.", file=sys.stderr)
    emit(
        set_lesson(
            client,
            class_id=args.class_id,
            date=args.date,
            title=args.title,
            text=args.text,
            homework=args.homework,
            notes=args.notes,
            unit_id=args.unit_id,
            sections=_sections_from(args, client),
            standards=args.standard if args.standard else None,
            assignments=args.assignment if args.assignment else None,
            # A dry run must not upload anything, so resolving --attach waits
            # for the real run.
            attach=None if args.dry_run else _attachments_from(args, client),
            attach_pending=list(args.attach) if args.dry_run else None,
            dry_run=args.dry_run,
        )
    )


def _require_class_id(item: JsonObject, args: argparse.Namespace, index: int) -> Id:
    """A missing class id is a user error, not a zero.

    `intish` turns an absent integer into "0", which here would post lessons
    to class 0.
    """
    class_id = item.get("class_id", args.class_id)
    if class_id in (None, ""):
        raise UsageError(f"Item {index} has no class_id and --class-id was not given.")
    return as_id(class_id, where=f"item {index} class_id")


BULK_KEYS = {
    "class_id",
    "date",
    "title",
    "text",
    "homework",
    "notes",
    "unit_id",
    "sections",
}


def _layout_reader(
    args: argparse.Namespace,
) -> Callable[[], list[LessonSection]]:
    """The account's lesson-section layout, fetched at most once per run.

    Only a section named by label needs it.
    """
    return functools.cache(lambda: lesson_sections(client_from(args)))


def _bulk_sections(
    item: JsonObject, layout: Callable[[], list[LessonSection]], index: int
) -> dict[int, str] | None:
    """Read a bulk item's `sections` map, resolving labels the same as --section."""
    raw = item.get("sections")
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise UsageError(f"Item {index}: `sections` must be an object.")
    resolved: dict[int, str] = {}
    for key, value in raw.items():
        known = [] if str(key).strip().isdigit() else layout()
        resolved[resolve_section(known, str(key))] = str(value)
    return resolved


def _read_bulk_file(path: str) -> list[JsonValue]:
    """The bulk file, or stdin when it is `-`."""
    try:
        text = read_stdin() if path == STDIN else Path(path).read_text()
        items = json.loads(text)
    except (OSError, ValueError) as exc:
        where = "stdin" if path == STDIN else path
        raise UsageError(f"Could not read {where}: {exc}") from exc
    if not isinstance(items, list):
        where = "stdin" if path == STDIN else path
        raise UsageError(f"{where} must contain a JSON list of lesson objects.")
    return items


def cmd_lessons_bulk(args: argparse.Namespace) -> None:
    """Write many lessons from a JSON file.

    A list of objects taking the same keys as `lessons set`, sent one at a
    time in order. With --journal each item is recorded as it lands, so
    --resume skips what already went through.
    """
    items = _read_bulk_file(args.file)
    journal = open_journal(args.journal, resume=args.resume)

    layout = _layout_reader(args)
    entries = [_validate(item, args, layout, index) for index, item in enumerate(items)]
    prepared = [
        lesson_payload(
            class_id=entry["class_id"],
            date=entry["date"],
            title=entry.get("title"),
            text=entry.get("text"),
            homework=entry.get("homework"),
            notes=entry.get("notes"),
            unit_id=entry.get("unit_id"),
            sections=entry.get("sections"),
        )[0]
        for entry in entries
    ]

    client = client_from(args)
    if args.dry_run:
        # One read per item, the same trade `lessons set --dry-run` makes: a
        # preview built without the carry-over shows this write blanking text
        # the real one keeps.
        emit([_write(client, entry, dry_run=True) for entry in entries])
        return

    closed = no_school_dates(client)
    # `closed` holds the server's zero-padded dates, so a raw "9/7/2026" would
    # miss the warning.
    hit = sorted({e["date"] for e in entries if e["date"] in closed})
    if hit:
        print(
            f"warning: no-school day(s) in this batch: {', '.join(hit)}",
            file=sys.stderr,
        )
    results: list[Result] = []
    failures = skipped = 0
    for index, (entry, payload) in enumerate(zip(entries, prepared, strict=True)):
        key = key_for(entry["class_id"], entry["date"])
        digest = payload_hash(payload)
        if journal is not None and journal.already_written(key, digest):
            skipped += 1
            results.append({"ok": True, "index": index, "skipped": True, "key": key})
            continue
        try:
            written = _write(client, entry)
        except PlanbookError as exc:
            failures += 1
            results.append({"ok": False, "index": index, "error": str(exc)})
            _journal_write(journal, key, digest, index, "failed", error=exc)
            if not args.keep_going:
                emit(_bulk_summary(results, failures, skipped, journal))
                raise SystemExit(1) from None
        else:
            results.append(written)
            _journal_write(journal, key, digest, index, "written", after=written)
    emit(_bulk_summary(results, failures, skipped, journal))
    if failures:
        raise SystemExit(1)


def _write(client: PlanbookClient, entry: BulkItem, *, dry_run: bool = False) -> Result:
    """One bulk item, through the same call the preview and the write share."""
    return set_lesson(
        client,
        class_id=entry["class_id"],
        date=entry["date"],
        title=entry.get("title"),
        text=entry.get("text"),
        homework=entry.get("homework"),
        notes=entry.get("notes"),
        unit_id=entry.get("unit_id"),
        sections=entry.get("sections"),
        dry_run=dry_run,
    )


def _validate(
    item: JsonValue,
    args: argparse.Namespace,
    layout: Callable[[], list[LessonSection]],
    index: int,
) -> BulkItem:
    """Check one bulk entry and return it in a shape the write loop can use.

    Every later step trusts this, so nothing downstream re-checks.
    """
    if not isinstance(item, dict):
        raise UsageError(f"Item {index} is not an object.")
    if "date" not in item:
        raise UsageError(f"Item {index} is missing 'date'.")
    unknown = set(item) - BULK_KEYS
    if unknown:
        raise UsageError(
            f"Item {index} has unknown key(s): {', '.join(sorted(unknown))}. "
            f"Accepted: {', '.join(sorted(BULK_KEYS))}."
        )
    entry = BulkItem(
        class_id=_require_class_id(item, args, index),
        # Zero-padded here, so the no-school check and the journal key match
        # the server's form.
        date=parse_date(str(item["date"])),
    )
    for key in ("title", "text", "homework", "notes"):
        if key not in item:
            continue
        value = item[key]
        if not isinstance(value, str):
            raise UsageError(
                f"Item {index}: '{key}' must be a string, got {type(value).__name__}."
            )
        entry[key] = value
    if item.get("unit_id") is not None:
        entry["unit_id"] = as_id(item["unit_id"], where=f"item {index} unit_id")
    sections = _bulk_sections(item, layout, index)
    if sections is not None:
        entry["sections"] = sections
    return entry


def _journal_write(
    journal: Journal | None,
    key: str,
    digest: str,
    index: int,
    status: str,
    *,
    after: Result | None = None,
    error: PlanbookError | None = None,
) -> None:
    if journal is None:
        return
    entry: Result = {
        "key": key,
        "index": index,
        "payload_sha256": digest,
        "status": status,
    }
    if after is not None:
        entry["after"] = after
    if error is not None:
        entry["error"] = error.to_dict()["error"]
    journal.record(entry)


def _bulk_summary(
    results: list[Result],
    failures: int,
    skipped: int,
    journal: Journal | None,
) -> Result:
    summary: Result = {
        "written": len(results) - failures - skipped,
        "skipped": skipped,
        "failed": failures,
        "results": results,
    }
    if journal is not None:
        summary["journal"] = str(journal.path)
    return summary


def cmd_lessons_week(args: argparse.Namespace) -> None:
    client = client_from(args)
    if args.raw:
        emit(get_week(client, monday=args.monday, weeks=args.weeks))
        return
    emit(
        read_week(client, monday=args.monday, weeks=args.weeks, saved_only=not args.all)
    )


def cmd_lessons_get(args: argparse.Namespace) -> None:
    found = find_lesson(client_from(args), class_id=args.class_id, date=args.date)
    if found is None:
        emit({"found": False, "class_id": args.class_id, "date": args.date})
        return
    emit(found if args.raw else projection.lesson(found, date=args.date))


def cmd_lessons_delete(args: argparse.Namespace) -> None:
    emit(
        delete_lesson(
            client_from(args),
            class_id=args.class_id,
            date=args.date,
            dry_run=args.dry_run,
        )
    )
