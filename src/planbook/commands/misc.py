"""Miscellaneous command callbacks."""

from __future__ import annotations

import argparse

from .. import api
from ..cli_support import client_from, emit, teacher_id_from, year_id_from
from ..endpoints import ENDPOINTS
from ..errors import UsageError


def cmd_schedule_special_days(args: argparse.Namespace) -> None:
    emit(
        api.special_days(
            client_from(args),
            teacher_id=teacher_id_from(args),
            year_id=year_id_from(args),
            school_id=args.school_id,
        )
    )


def cmd_settings(args: argparse.Namespace) -> None:
    emit(api.settings(client_from(args)))


def cmd_standards(args: argparse.Namespace) -> None:
    emit(api.standards(client_from(args), search=args.search or "", raw=args.raw))


def cmd_simple_read(args: argparse.Namespace) -> None:
    emit(api.simple_read(client_from(args), args.command, raw=args.raw))


def cmd_attachments_list(args: argparse.Namespace) -> None:
    emit(api.list_attachments(client_from(args), teacher_id=teacher_id_from(args)))


def cmd_attachments_upload(args: argparse.Namespace) -> None:
    client = client_from(args)
    emit([api.upload_attachment(client, f) for f in args.files])


def cmd_endpoints(_args: argparse.Namespace) -> None:
    emit([{"path": p, "status": s, "description": d} for p, s, d in ENDPOINTS])


def cmd_raw(args: argparse.Namespace) -> None:
    """POST to any endpoint. The escape hatch for unmapped calls."""
    payload: dict[str, str] = {}
    for pair in args.field:
        if "=" not in pair:
            raise UsageError(f"--field expects key=value, got {pair!r}")
        key, value = pair.split("=", 1)
        payload[key] = value
    if args.dry_run:
        emit(
            {
                "dry_run": True,
                "method": "GET" if args.get else ("POST-json" if args.json else "POST"),
                "endpoint": args.path,
                "payload": payload,
            }
        )
        return
    client = client_from(args)
    if args.get:
        emit(client.get(args.path, payload))
    elif args.json:
        emit(client.post_json(args.path, dict(payload)))
    else:
        emit(client.post(args.path, payload))


# --------------------------------------------------------------------------
