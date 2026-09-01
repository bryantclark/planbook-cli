"""The self-describing manifest behind `planbook schema`.

One JSON document describing every command and flag, so an agent never has to
parse `--help` prose. Generated from the parser, so it cannot drift.
"""

from __future__ import annotations

import argparse

from . import __version__
from .contract import CONTRACT_VERSION, EXIT_CODES
from .errors import ERROR_KINDS
from .types import Result
from .wire import DAY_LETTERS

#: argparse `type` callables mapped to the name an agent should read.
_TYPE_NAMES = {"_date": "date", "int": "integer", "str": "string"}


def _type_of(action: argparse.Action) -> str:
    if isinstance(action, argparse._StoreTrueAction | argparse._StoreConstAction):
        return "boolean"
    if action.type is None:
        return "string"
    name = getattr(action.type, "__name__", str(action.type))
    return _TYPE_NAMES.get(name, name)


def _argument(action: argparse.Action) -> Result:
    flags = list(action.option_strings)
    entry: Result = {
        "name": flags[-1] if flags else action.dest,
        "dest": action.dest,
        "positional": not flags,
        "required": bool(action.required),
        "type": _type_of(action),
        "repeatable": isinstance(action, argparse._AppendAction),
        "help": action.help or None,
    }
    if action.choices:
        entry["choices"] = list(action.choices)
    if action.default not in (None, False, [], 0):
        entry["default"] = action.default
    if action.metavar:
        entry["metavar"] = action.metavar
    return entry


def _subparsers(
    parser: argparse.ArgumentParser,
) -> argparse._SubParsersAction[argparse.ArgumentParser] | None:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action
    return None


def _commands(
    parser: argparse.ArgumentParser, path: list[str], help_text: str | None = None
) -> list[Result]:
    sub = _subparsers(parser)
    if sub is None:
        return [_command(parser, path, help_text)]
    # argparse keeps a subcommand's one-line help on the parent's pseudo-action,
    # not on the child parser, so read it from there.
    helps = {a.dest: a.help for a in sub._choices_actions}
    out: list[Result] = []
    for name, child in sub.choices.items():
        out.extend(_commands(child, [*path, name], helps.get(name)))
    return out


def _command(
    parser: argparse.ArgumentParser, path: list[str], help_text: str | None
) -> Result:
    args = [
        _argument(a)
        for a in parser._actions
        if not isinstance(a, argparse._HelpAction | argparse._SubParsersAction)
        and a.help is not argparse.SUPPRESS
    ]
    dests = {a["dest"] for a in args}
    # Declared at registration (see cli.marks), not guessed from the command
    # name: `raw` writes and is not called "delete".
    marks = getattr(parser, "planbook_marks", ())
    # Advertise stdin flags: that is how an agent passes HTML without quoting.
    for argument in args:
        if argument["dest"] in getattr(parser, "planbook_stdin", ()):
            argument["accepts_stdin"] = True
    entry: Result = {
        "command": " ".join(path),
        "help": help_text or parser.description,
        "writes": "writes" in marks or "destructive" in marks,
        "dry_run": "dry_run" in dests,
        "destructive": "destructive" in marks,
        "arguments": args,
    }
    if "id_only" in dests:
        entry["returns_id"] = True
    when = parser.get_default("_destructive_when")
    if when:
        # Destructive down one branch only, so name the flag that does it.
        entry["destructive_when"] = when
    return entry


def manifest(parser: argparse.ArgumentParser) -> Result:
    """Everything an agent needs to drive this CLI without reading `--help`."""
    return {
        "contract": CONTRACT_VERSION,
        "version": __version__,
        "output": {
            "stdout": "one JSON document on success, empty on failure",
            "stderr": "diagnostics; with --error-json, one JSON error object",
            "branch_on": "exit code, before parsing stdout",
        },
        "exit_codes": {str(k): v for k, v in EXIT_CODES.items()},
        "errors": [
            {
                "kind": err.kind,
                "code": err.exit_code,
                "retryable": err.retryable,
                "remedy": err.remedy,
            }
            for err in ERROR_KINDS
        ],
        "formats": {
            "date": "MM/DD/YYYY",
            "time": "24-hour (14:30) or 12-hour (2:30 PM); stored 12-hour",
            "day_letters": dict(DAY_LETTERS),
            "lesson_text": "HTML or plain text",
        },
        "conventions": {
            "id_key": "id",
            "raw_flag": (
                "--raw returns the untouched wire body, on the commands whose "
                "arguments list it"
            ),
            "stdin": "`-` on a text flag reads that value from stdin",
            "destructive_policy": (
                "--yes is required when a delete also destroys records you did "
                "not name, and on every `raw` request but --get, whose target "
                "this tool cannot read; --dry-run reports the full blast "
                "radius first"
            ),
        },
        "commands": _commands(parser, []),
    }
