"""Event command callbacks."""

from __future__ import annotations

import argparse

from .. import api
from ..cli import client_from, emit


def cmd_events_list(args: argparse.Namespace) -> None:
    emit(
        api.list_events(
            client_from(args),
            start=args.start or "",
            end=args.end or "",
            limit=args.limit,
            search=args.search or "",
        )
    )


def cmd_events_create(args: argparse.Namespace) -> None:
    if args.dry_run:
        emit(
            {
                "dry_run": True,
                "endpoint": "/addEvent",
                "payload": api.event_payload(
                    {
                        "repeats": args.repeats,
                        "eventTitle": args.title,
                        "eventDate": args.date,
                        "endDate": args.end_date or args.date,
                        "eventText": args.text or "",
                        "eventStartTime": args.start_time or "",
                        "eventEndTime": args.end_time or "",
                        "privateFlag": args.private,
                        "noSchool": args.no_school,
                    }
                ),
            }
        )
        return
    client = client_from(args)
    emit(
        api.create_event(
            client,
            title=args.title,
            date=args.date,
            end_date=args.end_date,
            text=args.text or "",
            start_time=args.start_time or "",
            end_time=args.end_time or "",
            private=args.private,
            no_school=args.no_school,
            repeats=args.repeats,
        )
    )


def cmd_events_delete(args: argparse.Namespace) -> None:
    emit(
        api.delete_event(
            client_from(args),
            event_id=args.event_id,
            occurrence_only=args.occurrence_only,
        )
    )
