"""Event command callbacks."""

from __future__ import annotations

import argparse

from ..cli_support import client_from, emit, emit_created, resolve_stdin
from ..resources.events import create_event, delete_event, list_events, raw_events


def cmd_events_list(args: argparse.Namespace) -> None:
    emit(
        (raw_events if args.raw else list_events)(
            client_from(args),
            start=args.start or "",
            end=args.end or "",
            limit=args.limit,
            search=args.search or "",
        )
    )


def cmd_events_create(args: argparse.Namespace) -> None:
    resolve_stdin(args, "text")
    # --no-school counts the lessons it would delete, so it needs a session
    # even for --dry-run. Every other preview is offline.
    offline = args.dry_run and not args.no_school
    emit_created(
        args,
        create_event(
            None if offline else client_from(args),
            title=args.title,
            date=args.date,
            end_date=args.end_date,
            text=args.text or "",
            start_time=args.start_time or "",
            end_time=args.end_time or "",
            private=args.private,
            no_school=args.no_school,
            repeats=args.repeats,
            force=args.force,
            dry_run=args.dry_run,
        ),
    )


def cmd_events_delete(args: argparse.Namespace) -> None:
    emit(
        delete_event(
            client_from(args),
            event_id=args.event_id,
            occurrence_only=args.occurrence_only,
            dry_run=args.dry_run,
            confirmed=args.yes,
        )
    )
