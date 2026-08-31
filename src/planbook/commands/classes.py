"""Class command callbacks."""

from __future__ import annotations

import argparse

from ..cli_support import client_from, emit, emit_created
from ..errors import UsageError
from ..resources.classes import (
    create_class,
    delete_class,
    get_class,
    list_classes,
    raw_classes,
    update_class,
)
from ..wire import parse_day_times, parse_days


def cmd_classes_list(args: argparse.Namespace) -> None:
    client = client_from(args)
    emit(raw_classes(client) if args.raw else list_classes(client))


def cmd_classes_create(args: argparse.Namespace) -> None:
    # Validate before touching auth: a typo in --days is a usage error, not a
    # demand that you sign in first.
    days = parse_days(args.days)
    emit_created(
        args,
        create_class(
            None if args.dry_run else client_from(args),
            name=args.name,
            start_date=args.start,
            end_date=args.end,
            days=days,
            color=args.color,
            description=args.description or "",
            times=parse_day_times(args.time, days),
            lesson_layout_id=args.lesson_layout_id,
            dry_run=args.dry_run,
        ),
    )


def cmd_classes_update(args: argparse.Namespace) -> None:
    days = parse_days(args.days) if args.days else None
    if args.time and any("=" not in spec for spec in args.time) and days is None:
        raise UsageError(
            "A bare --time needs --days to know which days it applies to. "
            "Use --time M=9:00-9:50 to set one day without changing the schedule."
        )
    emit(
        update_class(
            client_from(args),
            class_id=args.class_id,
            name=args.name,
            start_date=args.start,
            end_date=args.end,
            days=days,
            color=args.color,
            description=args.description,
            times=parse_day_times(args.time, days) if args.time else None,
            dry_run=args.dry_run,
        )
    )


def cmd_classes_get(args: argparse.Namespace) -> None:
    emit(get_class(client_from(args), args.class_id))


def cmd_classes_delete(args: argparse.Namespace) -> None:
    emit(
        delete_class(
            client_from(args),
            class_id=args.class_id,
            dry_run=args.dry_run,
            confirmed=args.yes,
        )
    )
