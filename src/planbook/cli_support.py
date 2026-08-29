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
    teacher_id = getattr(args, "teacher_id", None) or pbtoken.describe(
        config.load_session()
    ).get("account_id")
    if not teacher_id:
        raise UsageError("Could not determine a teacher id; pass --teacher-id.")
    return teacher_id
