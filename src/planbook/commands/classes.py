"""Class command callbacks."""

from __future__ import annotations

import argparse

from .. import api
from ..cli import client_from, emit
from ..errors import UsageError


def cmd_classes_list(args: argparse.Namespace) -> None:
    emit(api.list_classes(client_from(args), raw=args.raw))


def cmd_classes_create(args: argparse.Namespace) -> None:
    # Validate before touching auth: a typo in --days should be a usage error,
    # not a demand that you sign in first.
    days = api.parse_days(args.days)
    if args.dry_run:
        emit(
            {
                "dry_run": True,
                "endpoint": "/addClass",
                "payload": api.class_payload(
                    name=args.name,
                    start_date=args.start,
                    end_date=args.end,
                    days=days,
                    color=args.color,
                    description=args.description or "",
                    times=api.parse_day_times(args.time, days),
                    lesson_layout_id=args.lesson_layout_id,
                ),
            }
        )
        return
    client = client_from(args)
    emit(
        api.create_class(
            client,
            name=args.name,
            start_date=args.start,
            end_date=args.end,
            days=days,
            color=args.color,
            description=args.description or "",
            times=api.parse_day_times(args.time, days),
            lesson_layout_id=args.lesson_layout_id,
        )
    )


def cmd_classes_update(args: argparse.Namespace) -> None:
    days = api.parse_days(args.days) if args.days else None
    if args.time and any("=" not in spec for spec in args.time) and days is None:
        raise UsageError(
            "A bare --time needs --days to know which days it applies to. "
            "Use --time M=9:00-9:50 to set one day without changing the schedule."
        )
    emit(
        api.update_class(
            client_from(args),
            class_id=args.class_id,
            name=args.name,
            start_date=args.start,
            end_date=args.end,
            days=days,
            color=args.color,
            description=args.description,
            times=api.parse_day_times(args.time, days) if args.time else None,
        )
    )


def cmd_classes_get(args: argparse.Namespace) -> None:
    emit(api.get_class(client_from(args), args.class_id))


def cmd_classes_delete(args: argparse.Namespace) -> None:
    if not args.yes:
        raise UsageError(
            "Deleting a class also deletes every lesson in it, permanently. "
            "Pass --yes to confirm."
        )
    emit(api.delete_class(client_from(args), class_id=args.class_id))
