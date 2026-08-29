"""Miscellaneous command callbacks."""

from __future__ import annotations

import argparse

from .. import api, config
from .. import token as pbtoken
from ..cli import client_from, emit
from ..endpoints import ENDPOINTS
from ..errors import UsageError


def cmd_schedule_special_days(args: argparse.Namespace) -> None:
    emit(
        api.special_days(
            client_from(args),
            teacher_id=args.teacher_id,
            year_id=args.year_id,
            school_id=args.school_id,
        )
    )


def cmd_settings(args: argparse.Namespace) -> None:
    emit(api.settings(client_from(args)))


def cmd_standards(args: argparse.Namespace) -> None:
    emit(api.standards(client_from(args), search=args.search or "", raw=args.raw))


def cmd_simple_read(args: argparse.Namespace) -> None:
    emit(api.simple_read(client_from(args), args.command, raw=args.raw))


def _teacher_id(args: argparse.Namespace) -> object:
    teacher_id = getattr(args, "teacher_id", None) or pbtoken.describe(
        config.load_session()
    ).get("account_id")
    if not teacher_id:
        raise UsageError("Could not determine a teacher id; pass --teacher-id.")
    return teacher_id


def cmd_attachments_list(args: argparse.Namespace) -> None:
    emit(api.list_attachments(client_from(args), teacher_id=_teacher_id(args)))


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
        emit({"dry_run": True, "endpoint": args.path, "payload": payload})
        return
    emit(client_from(args).post(args.path, payload))


# --------------------------------------------------------------------------
