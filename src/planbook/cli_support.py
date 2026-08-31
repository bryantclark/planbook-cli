"""Helpers shared by the command modules."""

from __future__ import annotations

import argparse
import json
import sys

from . import config
from . import token as pbtoken
from .client import PlanbookClient
from .errors import UsageError
from .narrow import as_id, records
from .types import Id, Result


def emit(value: object) -> None:
    """Write one JSON document to stdout. Nothing else ever goes there."""
    json.dump(value, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")


def emit_created(args: argparse.Namespace, result: Result) -> None:
    """Emit a create result, honouring --id-only.

    `--id-only` hands back `{"id": N}`, so a caller chaining two writes never
    has to re-list.
    """
    if getattr(args, "id_only", False) and not result.get("dry_run"):
        emit({"id": result.get("id")})
        return
    emit(result)


STDIN = "-"


def read_stdin() -> str:
    """The whole of stdin, read once per run.

    Every text flag takes `-`, so HTML lesson bodies never go through shell
    quoting.
    """
    global _STDIN_TEXT
    if _STDIN_TEXT is None:
        text = sys.stdin.read()
        # The shell's trailing newline is not part of the value.
        _STDIN_TEXT = text[:-1] if text.endswith("\n") else text
    return _STDIN_TEXT


_STDIN_TEXT: str | None = None


def resolve_stdin(args: argparse.Namespace, *names: str) -> None:
    """Replace any named argument whose value is `-` with the text on stdin.

    stdin reads once, so two `-` flags in one call is a usage error.
    """
    hits = [n for n in names if getattr(args, n, None) == STDIN]
    hits += [
        f"section {spec.partition('=')[0]}"
        for spec in getattr(args, "section", None) or []
        if spec.partition("=")[2] == STDIN
    ]
    if len(hits) > 1:
        flags = ", ".join(
            n if n.startswith("section ") else "--" + n.replace("_", "-") for n in hits
        )
        raise UsageError(f"Only one argument can read stdin; {flags} all asked for it.")
    for name in hits:
        if not name.startswith("section "):
            setattr(args, name, read_stdin())


def client_from(args: argparse.Namespace) -> PlanbookClient:
    return PlanbookClient(config.load_session(), verbose=args.verbose)


def teacher_id_from(args: argparse.Namespace) -> Id:
    """The teacher id, from the flag, the token, or failing that a live call.

    Not every issuer puts the account id in the token; `/getClasses2` reports
    it on every class.
    """
    teacher_id: Id | None = getattr(args, "teacher_id", None) or _claim("account_id")
    if not teacher_id:
        client = client_from(args)
        body = client.require(
            client.post("/getClasses2"), "classes", where="getClasses2"
        )
        teacher_id = next(
            (
                as_id(c["teacherId"], where="getClasses2.classes[].teacherId")
                for c in records(body["classes"], where="getClasses2.classes")
                if c.get("teacherId")
            ),
            None,
        )
    if teacher_id is None:
        raise UsageError("Could not determine a teacher id; pass --teacher-id.")
    return teacher_id


def year_id_from(args: argparse.Namespace) -> Id:
    """The school-year id, from the flag, the token, or a live call."""
    year_id: Id | None = getattr(args, "year_id", None) or _claim("year_id")
    if not year_id:
        client = client_from(args)
        body = client.require(
            client.post("/getClasses2"), "currentYearId", where="getClasses2"
        )
        year_id = as_id(body["currentYearId"], where="getClasses2.currentYearId")
    if year_id is None:
        raise UsageError("Could not determine a year id; pass --year-id.")
    return year_id


def _claim(name: str) -> Id | None:
    """One claim out of the stored token, when it is an id-shaped one."""
    value = pbtoken.describe(config.load_session()).get(name)
    return (
        value if isinstance(value, int | str) and not isinstance(value, bool) else None
    )
