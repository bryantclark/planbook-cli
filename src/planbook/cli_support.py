"""Helpers shared by the command modules."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from . import config
from . import token as pbtoken
from .client import PlanbookClient
from .errors import UsageError


def emit(value: Any) -> None:
    """Write one JSON document to stdout. Nothing else ever goes there."""
    json.dump(value, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")


def client_from(args: argparse.Namespace) -> PlanbookClient:
    return PlanbookClient(config.load_session(), verbose=args.verbose)


def teacher_id_from(args: argparse.Namespace) -> Any:
    """The teacher id, from the flag, the token, or failing that a live call.

    Not every issuer puts the account id in the token, so the last resort is
    `/getClasses2`, which reports it on every class.
    """
    teacher_id = getattr(args, "teacher_id", None) or pbtoken.describe(
        config.load_session()
    ).get("account_id")
    if not teacher_id:
        classes = client_from(args).post("/getClasses2").get("classes") or []
        teacher_id = next(
            (c.get("teacherId") for c in classes if c.get("teacherId")), None
        )
    if not teacher_id:
        raise UsageError("Could not determine a teacher id; pass --teacher-id.")
    return teacher_id


def year_id_from(args: argparse.Namespace) -> Any:
    """The school-year id, from the flag, the token, or a live call."""
    year_id = getattr(args, "year_id", None) or pbtoken.describe(
        config.load_session()
    ).get("year_id")
    if not year_id:
        year_id = client_from(args).post("/getClasses2").get("currentYearId")
    if not year_id:
        raise UsageError("Could not determine a year id; pass --year-id.")
    return year_id
