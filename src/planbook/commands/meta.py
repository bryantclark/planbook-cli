"""Commands that describe the CLI itself rather than the account."""

from __future__ import annotations

import argparse
import os

from .. import config, schema
from .. import token as pbtoken
from ..cli_support import emit
from ..client import PlanbookClient
from ..contract import CONTRACT_VERSION
from ..endpoints import ENDPOINTS
from ..resources.classes import list_classes


def cmd_schema(_args: argparse.Namespace) -> None:
    """Dump the whole command surface as JSON, generated from the parser."""
    from ..cli import build_parser

    emit(schema.manifest(build_parser()))


def cmd_endpoints(_args: argparse.Namespace) -> None:
    emit([{"path": p, "status": s, "description": d} for p, s, d in ENDPOINTS])


def cmd_check(args: argparse.Namespace) -> None:
    """The preflight: is the session good, for how long, and which classes.

    `/getClasses2` answers all three, so this is one round trip.
    """
    raw = config.load_session()
    info = pbtoken.describe(raw)
    client = PlanbookClient(raw, verbose=args.verbose)
    body = list_classes(client)
    emit(
        {
            "contract": CONTRACT_VERSION,
            "authenticated": True,
            "source": "env" if config.TOKEN_ENV in os.environ else "file",
            "email": info.get("email"),
            "account_id": info.get("account_id"),
            "expires_in_hours": info.get("expires_in_hours"),
            "current_year_id": body["current_year_id"],
            "classes": [
                {
                    "id": c["id"],
                    "name": c["name"],
                    "start_date": c["start_date"],
                    "end_date": c["end_date"],
                    "days": [day for day, v in c["schedule"].items() if v["teaches"]],
                }
                for c in body["classes"]
            ],
        }
    )
