"""Unit command callbacks."""

from __future__ import annotations

import argparse

from .. import api
from ..cli_support import client_from, emit


def _unit_dry(args: argparse.Namespace, action: str) -> api.Payload:
    return api.unit_payload(
        action=action,
        class_id=args.class_id,
        unit_id=getattr(args, "unit_id", 0) or 0,
        number=getattr(args, "number", "") or "",
        title=getattr(args, "title", "") or "",
        description=getattr(args, "description", "") or "",
        start=getattr(args, "start", "") or "",
        end=getattr(args, "end", "") or "",
    )


def cmd_units_list(args: argparse.Namespace) -> None:
    emit(api.list_units(client_from(args), raw=args.raw))


def cmd_units_create(args: argparse.Namespace) -> None:
    if args.dry_run:
        emit(
            {
                "dry_run": True,
                "endpoint": "/updateUnit",
                "payload": _unit_dry(args, "A"),
            }
        )
        return
    client = client_from(args)
    emit(
        api.create_unit(
            client,
            class_id=args.class_id,
            number=args.number,
            title=args.title,
            description=args.description or "",
            start=args.start or "",
            end=args.end or "",
        )
    )


def cmd_units_update(args: argparse.Namespace) -> None:
    if args.dry_run:
        emit(
            {
                "dry_run": True,
                "endpoint": "/updateUnit",
                "payload": _unit_dry(args, "U"),
            }
        )
        return
    client = client_from(args)
    emit(
        api.update_unit(
            client,
            unit_id=args.unit_id,
            class_id=args.class_id,
            number=args.number,
            title=args.title,
            description=args.description or "",
            start=args.start or "",
            end=args.end or "",
        )
    )


def cmd_units_delete(args: argparse.Namespace) -> None:
    if args.dry_run:
        emit(
            {
                "dry_run": True,
                "endpoint": "/updateUnit",
                "payload": _unit_dry(args, "D"),
            }
        )
        return
    client = client_from(args)
    emit(api.delete_unit(client, unit_id=args.unit_id, class_id=args.class_id))
