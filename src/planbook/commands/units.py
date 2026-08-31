"""Unit command callbacks."""

from __future__ import annotations

import argparse

from ..cli_support import client_from, emit, emit_created
from ..resources.units import (
    create_unit,
    delete_unit,
    list_units,
    raw_units,
    update_unit,
)


def cmd_units_list(args: argparse.Namespace) -> None:
    client = client_from(args)
    emit(raw_units(client) if args.raw else list_units(client))


def cmd_units_create(args: argparse.Namespace) -> None:
    emit_created(
        args,
        create_unit(
            None if args.dry_run else client_from(args),
            class_id=args.class_id,
            number=args.number,
            title=args.title,
            description=args.description or "",
            start=args.start or "",
            end=args.end or "",
            dry_run=args.dry_run,
        ),
    )


def cmd_units_update(args: argparse.Namespace) -> None:
    emit(
        update_unit(
            client_from(args),
            unit_id=args.unit_id,
            class_id=args.class_id,
            number=args.number,
            title=args.title,
            description=args.description,
            start=args.start,
            end=args.end,
            dry_run=args.dry_run,
        )
    )


def cmd_units_delete(args: argparse.Namespace) -> None:
    emit(
        delete_unit(
            client_from(args),
            unit_id=args.unit_id,
            class_id=args.class_id,
            dry_run=args.dry_run,
        )
    )
