"""Command-line surface.

Design notes, because this CLI is aimed at agents as much as people:

* Every command prints JSON to stdout. Nothing else goes to stdout, so the
  output is always safe to pipe into a parser.
* Human-readable diagnostics go to stderr.
* Exit codes are meaningful: 64 usage, 65 unexpected response shape,
  77 not authenticated, 1 everything else.
* Writes accept --dry-run, which prints the exact form payload instead of
  sending it.
"""

from __future__ import annotations

import argparse
import getpass
import json
import re
import sys
from pathlib import Path
from typing import Any

from . import __version__, api, auth, browser_auth, config
from .client import PlanbookClient
from .endpoints import ENDPOINTS
from .errors import PlanbookError, UsageError


def emit(value: Any) -> None:
    json.dump(value, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")


SESSION_RE = re.compile(r"SESSION=([0-9a-fA-F-]{36})")
UUID_RE = re.compile(r"^[0-9a-fA-F-]{36}$")


def extract_session(text: str) -> str | None:
    """Pull a SESSION value out of whatever the user pasted.

    Accepts the bare value, a full `Cookie:` header, or an entire command
    copied with DevTools' "Copy as cURL" - which is the least error-prone
    thing to ask someone for, since it is one right-click and cannot pick up
    the wrong cookie.
    """
    text = text.strip()
    if UUID_RE.match(text):
        return text
    match = SESSION_RE.search(text)
    return match.group(1) if match else None


def client_from(args: argparse.Namespace) -> PlanbookClient:
    return PlanbookClient(config.load_session(), verbose=args.verbose)


# --------------------------------------------------------------------------
# auth


def cmd_auth_login(args: argparse.Namespace) -> None:
    username = args.username or input("Email or user ID: ").strip()
    # Read the password from a TTY. It is never logged, never passed as an
    # argv value, and never written anywhere except the 0600 session file.
    password = getpass.getpass("Password: ")
    cookie = auth.login(username, password)
    path = config.save_session(cookie, username)
    emit({"ok": True, "stored": str(path), "username": username})


def cmd_auth_cookie(args: argparse.Namespace) -> None:
    """Store a SESSION cookie copied out of a signed-in browser.

    The way in for SSO accounts (Google, Microsoft, Clever, ClassLink,
    Apple), which the form login cannot drive.

    Prompts when the value is omitted. Prefer that: the cookie is a bearer
    credential for the whole account, and passing it as an argument leaves
    it in shell history and in the process list.
    """
    raw = args.value or getpass.getpass("Paste cookie, Cookie header, or curl: ")
    value = extract_session(raw)
    if not value:
        raise UsageError(
            "No SESSION value found in that input. Paste either the cookie "
            "value itself, a whole Cookie: header, or a request copied with "
            "DevTools -> right-click -> Copy as cURL."
        )

    # Verify before storing. A cookie that does not work should fail here,
    # not three commands later with a confusing error - and DevTools shows an
    # anonymous SESSION next to the real one, so a wrong paste is easy.
    if not args.no_verify:
        from .auth import _works
        if not _works(value):
            raise UsageError(
                "That SESSION was found but the API rejects it.\n"
                "It is most likely an anonymous session. Get the authenticated "
                "one from DevTools -> Network -> filter 'api.planbook.com' -> "
                "click getClasses2 -> right-click -> Copy as cURL, then paste "
                "the whole thing here."
            )

    path = config.save_session(value)
    emit({"ok": True, "stored": str(path), "verified": not args.no_verify})


def cmd_auth_browser(args: argparse.Namespace) -> None:
    """Sign in by opening a browser and waiting for the user to do it.

    Tries a silent refresh from the stored profile first, so a routine
    re-auth costs nothing and only a genuinely expired sign-in opens a
    window. --interactive forces the window.
    """
    if args.interactive:
        cookie = browser_auth.login_via_browser(
            timeout=args.timeout, channel=args.channel, profile=args.profile
        )
        interactive = True
    else:
        cookie, interactive = browser_auth.refresh_or_login(
            timeout=args.timeout, channel=args.channel, profile=args.profile
        )
    path = config.save_session(cookie)
    emit({
        "ok": True,
        "stored": str(path),
        "method": "browser",
        "interactive": interactive,
    })


def cmd_auth_status(args: argparse.Namespace) -> None:
    client = client_from(args)
    body = api.list_classes(client)
    emit({
        "authenticated": True,
        "source": "env" if config.SESSION_ENV in __import__("os").environ else "file",
        "current_year_id": body["current_year_id"],
        "class_count": len(body["classes"]),
    })


def cmd_auth_logout(args: argparse.Namespace) -> None:
    emit({"cleared": config.clear_session()})


# --------------------------------------------------------------------------
# classes


def cmd_classes_list(args: argparse.Namespace) -> None:
    emit(api.list_classes(client_from(args), raw=args.raw))


def cmd_classes_create(args: argparse.Namespace) -> None:
    days = api.parse_days(args.days)
    result = api.create_class(
        client_from(args),
        name=args.name,
        start_date=args.start,
        end_date=args.end,
        days=days,
        color=args.color,
        description=args.description or "",
    )
    emit({"ok": True, "name": args.name, "days": days, "response": result})


# --------------------------------------------------------------------------
# lessons


def cmd_lessons_set(args: argparse.Namespace) -> None:
    # A dry run must not need a session: it is the safe first step.
    client = None if args.dry_run else client_from(args)
    emit(api.set_lesson(
        client,
        class_id=args.class_id,
        date=args.date,
        title=args.title,
        text=args.text,
        homework=args.homework,
        notes=args.notes,
        unit_id=args.unit_id,
        dry_run=args.dry_run,
    ))


def cmd_lessons_bulk(args: argparse.Namespace) -> None:
    """Write many lessons from a JSON file.

    The file is a list of objects, each accepting the same keys as
    `lessons set`: class_id, date, title, text, homework, notes.
    Requests are sent one at a time, in order, deliberately: this is
    somebody's real planbook, not a load test.
    """
    try:
        items = json.loads(open(args.file).read())
    except (OSError, ValueError) as exc:
        raise UsageError(f"Could not read {args.file}: {exc}") from exc
    if not isinstance(items, list):
        raise UsageError(f"{args.file} must contain a JSON list of lesson objects.")

    client = None if args.dry_run else client_from(args)
    results, failures = [], 0
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise UsageError(f"Item {index} is not an object.")
        try:
            results.append(api.set_lesson(
                client,
                class_id=item.get("class_id", args.class_id),
                date=item["date"],
                title=item.get("title"),
                text=item.get("text"),
                homework=item.get("homework"),
                notes=item.get("notes"),
                unit_id=item.get("unit_id"),
                dry_run=args.dry_run,
            ))
        except KeyError as exc:
            raise UsageError(f"Item {index} is missing {exc}.") from exc
        except PlanbookError as exc:
            failures += 1
            results.append({"ok": False, "index": index, "error": str(exc)})
            if not args.keep_going:
                emit({"written": len(results) - failures, "failed": failures,
                      "results": results})
                raise SystemExit(1)
    emit({"written": len(results) - failures, "failed": failures, "results": results})
    if failures:
        raise SystemExit(1)


def cmd_lessons_week(args: argparse.Namespace) -> None:
    emit(api.get_week(client_from(args), monday=args.monday, weeks=args.weeks))


# --------------------------------------------------------------------------
# misc


def cmd_schedule_special_days(args: argparse.Namespace) -> None:
    emit(api.special_days(
        client_from(args),
        teacher_id=args.teacher_id,
        year_id=args.year_id,
        school_id=args.school_id,
    ))


def cmd_settings(args: argparse.Namespace) -> None:
    emit(api.settings(client_from(args)))


def cmd_standards(args: argparse.Namespace) -> None:
    emit(api.standards(client_from(args)))


def cmd_endpoints(args: argparse.Namespace) -> None:
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="planbook",
        description="Unofficial CLI for Planbook.com. Prints JSON on stdout.",
        epilog="Docs: AGENTS.md for agent usage, docs/API-NOTES.md for the API itself.",
    )
    parser.add_argument("--version", action="version", version=f"planbook-cli {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="log each request to stderr")
    sub = parser.add_subparsers(dest="command", required=True)

    # auth
    p_auth = sub.add_parser("auth", help="sign in and inspect the stored session")
    s_auth = p_auth.add_subparsers(dest="auth_command", required=True)
    a = s_auth.add_parser("login", help="sign in with email and password (prompts)")
    a.add_argument("--username", help="email or user ID; prompted for if omitted")
    a.set_defaults(func=cmd_auth_login)
    a = s_auth.add_parser("cookie", help="store a SESSION cookie from a browser (SSO accounts)")
    a.add_argument("value", nargs="?",
                   help="cookie value, Cookie header, or a 'Copy as cURL' paste; "
                        "prompted for (hidden) if omitted")
    a.add_argument("--no-verify", action="store_true",
                   help="store without checking the session against the API")
    a.set_defaults(func=cmd_auth_cookie)
    a = s_auth.add_parser(
        "browser",
        help="sign in by opening a browser (works with Google and other SSO)")
    a.add_argument("--timeout", type=int, default=300,
                   help="seconds to wait for sign-in (default 300)")
    a.add_argument("--channel", choices=["chrome", "msedge", "chromium"],
                   help="which browser to launch; tries chrome, then edge, then chromium")
    a.add_argument("--profile", type=Path,
                   help="browser profile directory (default: alongside the session file)")
    a.add_argument("--interactive", action="store_true",
                   help="always open a window; skip the silent refresh attempt")
    a.set_defaults(func=cmd_auth_browser)
    a = s_auth.add_parser("status", help="verify the stored session works")
    a.set_defaults(func=cmd_auth_status)
    a = s_auth.add_parser("logout", help="delete the stored session")
    a.set_defaults(func=cmd_auth_logout)

    # classes
    p_cls = sub.add_parser("classes", help="list and create classes")
    s_cls = p_cls.add_subparsers(dest="classes_command", required=True)
    c = s_cls.add_parser("list", help="list classes with their weekly schedule")
    c.add_argument("--raw", action="store_true", help="print the unmapped wire format")
    c.set_defaults(func=cmd_classes_list)
    c = s_cls.add_parser("create", help="create a class")
    c.add_argument("--name", required=True)
    c.add_argument("--start", required=True, metavar="MM/DD/YYYY")
    c.add_argument("--end", required=True, metavar="MM/DD/YYYY")
    c.add_argument("--days", default="MTWRF",
                   help="days taught, e.g. MTWRF (R=Thursday, U=Sunday)")
    c.add_argument("--color", default="#7ED321")
    c.add_argument("--description")
    c.set_defaults(func=cmd_classes_create)

    # lessons
    p_les = sub.add_parser("lessons", help="read and write lessons")
    s_les = p_les.add_subparsers(dest="lessons_command", required=True)
    l = s_les.add_parser("set", help="create or update one lesson (upsert by class+date)")
    l.add_argument("--class-id", dest="class_id", required=True)
    l.add_argument("--date", required=True, metavar="MM/DD/YYYY")
    l.add_argument("--title")
    l.add_argument("--text", help="lesson body; HTML is accepted")
    l.add_argument("--homework")
    l.add_argument("--notes")
    l.add_argument("--unit-id", dest="unit_id")
    l.add_argument("--dry-run", action="store_true",
                   help="print the form payload instead of sending it")
    l.set_defaults(func=cmd_lessons_set)
    l = s_les.add_parser("bulk", help="write many lessons from a JSON file")
    l.add_argument("file", help="JSON list of lesson objects")
    l.add_argument("--class-id", dest="class_id",
                   help="default class_id for items that omit one")
    l.add_argument("--keep-going", action="store_true",
                   help="continue after a failed item instead of stopping")
    l.add_argument("--dry-run", action="store_true")
    l.set_defaults(func=cmd_lessons_bulk)
    l = s_les.add_parser("week", help="fetch a week of lessons and events (partial mapping)")
    l.add_argument("--monday", required=True, metavar="MM/DD/YYYY")
    l.add_argument("--weeks", type=int, default=1)
    l.set_defaults(func=cmd_lessons_week)

    # schedule
    p_sch = sub.add_parser("schedule", help="school calendar")
    s_sch = p_sch.add_subparsers(dest="schedule_command", required=True)
    s = s_sch.add_parser("special-days", help="holidays and non-teaching days")
    s.add_argument("--teacher-id", dest="teacher_id", required=True)
    s.add_argument("--year-id", dest="year_id", required=True)
    s.add_argument("--school-id", dest="school_id", default=0)
    s.set_defaults(func=cmd_schedule_special_days)

    p = sub.add_parser("settings", help="account settings")
    p.set_defaults(func=cmd_settings)
    p = sub.add_parser("standards", help="standards available to the account")
    p.set_defaults(func=cmd_standards)
    p = sub.add_parser("endpoints", help="list known API endpoints and how well they are mapped")
    p.set_defaults(func=cmd_endpoints)

    p = sub.add_parser("raw", help="POST to any endpoint (escape hatch for unmapped calls)")
    p.add_argument("path", help="endpoint path, e.g. /getAssignments")
    p.add_argument("-F", "--field", action="append", default=[], metavar="KEY=VALUE",
                   help="form field; repeatable")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_raw)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except PlanbookError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.exit_code
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
