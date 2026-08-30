"""Lesson command callbacks."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .. import api
from ..cli_support import client_from, emit, teacher_id_from
from ..client import PlanbookClient
from ..errors import PlanbookError, UsageError


def _sections_from(
    args: argparse.Namespace, client: PlanbookClient | None
) -> dict[int, str] | None:
    """Resolve --section SPEC values to section indexes.

    Labels come from the account's lesson layout, so this only fetches
    settings when a label (rather than a number) is actually used.
    """
    if not args.section:
        return None
    resolved: dict[int, str] = {}
    known = None
    for spec in args.section:
        key, sep, value = spec.partition("=")
        if not sep:
            raise UsageError(
                f"--section {spec!r} needs KEY=TEXT, e.g. 4=... or Homework=..."
            )
        if not key.strip().isdigit() and known is None:
            known = api.lesson_sections(client or client_from(args))
        resolved[api.resolve_section(known or [], key)] = value
    return resolved


def cmd_lessons_sections(args: argparse.Namespace) -> None:
    emit(api.lesson_sections(client_from(args)))


def _attachments_from(
    args: argparse.Namespace, client: PlanbookClient | None
) -> list[dict[str, str]] | None:
    """Resolve --attach values: a local path is uploaded, a name is looked up."""
    if not args.attach:
        return None
    if client is None:
        raise UsageError("--attach needs a network connection; drop --dry-run.")
    return [
        api.resolve_attachment(client, ref, teacher_id=teacher_id_from(args))
        for ref in args.attach
    ]


def cmd_lessons_set(args: argparse.Namespace) -> None:
    if args.dry_run:
        # Offline on purpose: inspecting a payload is the safe first step and
        # must never need a session.
        payload, updated = api.lesson_payload(
            class_id=args.class_id,
            date=args.date,
            title=args.title,
            text=args.text,
            homework=args.homework,
            notes=args.notes,
            unit_id=args.unit_id,
            sections=_sections_from(args, None),
            standards=args.standard or None,
            assignments=args.assignment or None,
        )
        emit(
            {
                "dry_run": True,
                "endpoint": "/updateLesson",
                "payload": payload,
                "updated_fields": updated,
            }
        )
        return

    client = client_from(args)
    if args.date in api.no_school_dates(client):
        print(f"warning: {args.date} is marked as a no-school day.", file=sys.stderr)
    emit(
        api.set_lesson(
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
            attach=_attachments_from(args, client),
        )
    )


def _require_class_id(
    item: dict[str, Any], args: argparse.Namespace, index: int
) -> Any:
    """A missing class id is a user error, not a zero.

    `intish` turns absent integers into "0" because that is what the API
    wants for genuinely optional ids. Letting that default through here
    would post lessons to class 0.
    """
    class_id = item.get("class_id", args.class_id)
    if class_id in (None, ""):
        raise UsageError(f"Item {index} has no class_id and --class-id was not given.")
    return class_id


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


def _bulk_sections(
    item: dict[str, Any], args: argparse.Namespace, index: int
) -> dict[int, str] | None:
    """Read a bulk item's `sections` map, resolving labels the same as --section."""
    raw = item.get("sections")
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise UsageError(f"Item {index}: `sections` must be an object.")
    known = None
    resolved: dict[int, str] = {}
    for key, value in raw.items():
        if not str(key).strip().isdigit() and known is None:
            known = api.lesson_sections(client_from(args))
        resolved[api.resolve_section(known or [], str(key))] = value
    return resolved


def cmd_lessons_bulk(args: argparse.Namespace) -> None:
    """Write many lessons from a JSON file.

    A list of objects taking the same keys as `lessons set`. Sent one at a
    time, in order, on purpose: this is somebody's real planbook.
    """
    try:
        items = json.loads(Path(args.file).read_text())
    except (OSError, ValueError) as exc:
        raise UsageError(f"Could not read {args.file}: {exc}") from exc
    if not isinstance(items, list):
        raise UsageError(f"{args.file} must contain a JSON list of lesson objects.")

    # Validate everything before writing anything: a typo in item 40 should
    # not leave 39 lessons half-applied.
    for index, item in enumerate(items):
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
        _require_class_id(item, args, index)
        # Build every payload up front: it is pure, and it is what rejects an
        # item with nothing to write. SKILL.md promises a bad item cannot
        # half-apply a week, so that has to fail before the first send.
        api.lesson_payload(
            class_id=_require_class_id(item, args, index),
            date=item["date"],
            title=item.get("title"),
            text=item.get("text"),
            homework=item.get("homework"),
            notes=item.get("notes"),
            unit_id=item.get("unit_id"),
        )

    if args.dry_run:
        emit(
            [
                {
                    "dry_run": True,
                    "endpoint": "/updateLesson",
                    "payload": api.lesson_payload(
                        class_id=_require_class_id(item, args, index),
                        date=item["date"],
                        title=item.get("title"),
                        text=item.get("text"),
                        homework=item.get("homework"),
                        notes=item.get("notes"),
                        unit_id=item.get("unit_id"),
                        sections=_bulk_sections(item, args, index),
                    )[0],
                }
                for index, item in enumerate(items)
            ]
        )
        return

    client = client_from(args)
    closed = api.no_school_dates(client)
    hit = sorted({i["date"] for i in items if i.get("date") in closed})
    if hit:
        print(
            f"warning: no-school day(s) in this batch: {', '.join(hit)}",
            file=sys.stderr,
        )
    results, failures = [], 0
    for index, item in enumerate(items):
        try:
            results.append(
                api.set_lesson(
                    client,
                    class_id=_require_class_id(item, args, index),
                    date=item["date"],
                    title=item.get("title"),
                    text=item.get("text"),
                    homework=item.get("homework"),
                    notes=item.get("notes"),
                    unit_id=item.get("unit_id"),
                    sections=_bulk_sections(item, args, index),
                )
            )
        except PlanbookError as exc:
            failures += 1
            results.append({"ok": False, "index": index, "error": str(exc)})
            if not args.keep_going:
                emit(
                    {
                        "written": len(results) - failures,
                        "failed": failures,
                        "results": results,
                    }
                )
                raise SystemExit(1) from None
    emit({"written": len(results) - failures, "failed": failures, "results": results})
    if failures:
        raise SystemExit(1)


def cmd_lessons_week(args: argparse.Namespace) -> None:
    client = client_from(args)
    if args.raw:
        emit(api.get_week(client, monday=args.monday, weeks=args.weeks))
        return
    emit(
        api.read_week(
            client, monday=args.monday, weeks=args.weeks, saved_only=not args.all
        )
    )


def cmd_lessons_get(args: argparse.Namespace) -> None:
    lesson = api.find_lesson(client_from(args), class_id=args.class_id, date=args.date)
    emit(
        lesson
        if lesson is not None
        else {"found": False, "class_id": args.class_id, "date": args.date}
    )


def cmd_lessons_delete(args: argparse.Namespace) -> None:
    if args.dry_run:
        emit(
            {
                "dry_run": True,
                "endpoint": "/deleteLesson",
                "payload": {
                    "classId": str(args.class_id),
                    "customDate": args.date,
                    "userMode": "T",
                },
            }
        )
        return
    emit(api.delete_lesson(client_from(args), class_id=args.class_id, date=args.date))
