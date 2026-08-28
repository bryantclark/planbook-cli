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

import os

from . import __version__, api, auth, browser_auth, config
from . import browser_cookies
from . import token as pbtoken
from .client import PlanbookClient
from .endpoints import ENDPOINTS
from .errors import PlanbookError, UsageError


def emit(value: Any) -> None:
    json.dump(value, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")


_UNUSED_SESSION_RE = re.compile(r"SESSION=([0-9a-fA-F-]{36})")
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


def cmd_auth_token(args: argparse.Namespace) -> None:
    """Store a Planbook access token copied out of a signed-in browser.

    Accepts anything containing the token: the bare JWT, a Cookie header, or
    a whole "Copy as cURL" paste. Verifies before storing, because a token
    that does not work should fail here rather than three commands later.
    """
    raw = args.value or getpass.getpass("Paste token, cookie, or curl: ")
    value = pbtoken.extract(raw)
    if not value:
        raise UsageError(
            "No access token found in that input.\n"
            "Paste the JWT itself, or a request copied with DevTools -> "
            "Network -> right-click a call to api.planbook.com -> Copy as cURL. "
            "The token is the cookie named U|...|.accesstoken - NOT the SESSION "
            "cookie, which is not what authenticates you."
        )

    info = pbtoken.describe(value)
    if pbtoken.is_expired(value):
        raise UsageError(
            "That token has already expired. Reload Planbook in your browser "
            "and copy a fresh one."
        )

    if not args.no_verify:
        client = PlanbookClient(value, verbose=args.verbose)
        api.list_classes(client)  # raises NotAuthenticated if the token is bad

    path = config.save_session(value, info.get("email"))
    emit({
        "ok": True,
        "stored": str(path),
        "verified": not args.no_verify,
        "email": info.get("email"),
        "expires_in_hours": info.get("expires_in_hours"),
    })


def cmd_auth_import(args: argparse.Namespace) -> None:
    """Read the access token from a browser the user is already signed in to.

    The recommended path. Nothing is automated, so no identity provider gets
    suspicious, and there is nothing to copy by hand.
    """
    from .default_browser import default_browser_name

    preferred = args.browser
    if not preferred:
        name = default_browser_name()
        if name:
            preferred = name.split()[0].lower()

    for browser, candidate in browser_cookies.search(preferred):
        if pbtoken.is_expired(candidate):
            continue
        client = PlanbookClient(candidate, verbose=args.verbose)
        try:
            api.list_classes(client)
        except Exception:
            continue  # stale token from an old sign-in
        info = pbtoken.describe(candidate)
        path = config.save_session(candidate, info.get("email"))
        emit({
            "ok": True,
            "stored": str(path),
            "source": browser,
            "email": info.get("email"),
            "expires_in_hours": info.get("expires_in_hours"),
        })
        return

    report = browser_cookies.diagnose()
    lines = "\n".join(f"  {b:8} {status}" for b, status in report.items())
    from .errors import SIGN_IN_URL

    raise UsageError(
        "No usable Planbook token found in any local browser.\n" + lines + "\n\n"
        f"Sign in at {SIGN_IN_URL} first, then run `planbook auth import` again.\n"
        "If a browser above says 'locked', macOS denied Keychain access - rerun "
        "and choose Always Allow.\n"
        "If you would rather not grant that, use `planbook auth token` instead."
    )


def cmd_auth_browser(args: argparse.Namespace) -> None:
    """Sign in by opening a browser and waiting for the user to do it.

    Discouraged - see README. Kept because it needs no manual copying, and
    because it becomes the good path if Planbook ever registers an OAuth
    client.
    """
    if args.interactive:
        value = browser_auth.login_via_browser(
            timeout=args.timeout, channel=args.channel, profile=args.profile
        )
        interactive = True
    else:
        value, interactive = browser_auth.refresh_or_login(
            timeout=args.timeout, channel=args.channel, profile=args.profile
        )
    info = pbtoken.describe(value)
    path = config.save_session(value, info.get("email"))
    emit({
        "ok": True,
        "stored": str(path),
        "method": "browser",
        "interactive": interactive,
        "email": info.get("email"),
        "expires_in_hours": info.get("expires_in_hours"),
    })


def cmd_auth_status(args: argparse.Namespace) -> None:
    raw = config.load_session()
    info = pbtoken.describe(raw)
    client = PlanbookClient(raw, verbose=args.verbose)
    body = api.list_classes(client)
    emit({
        "authenticated": True,
        "source": "env" if config.TOKEN_ENV in os.environ else "file",
        "email": info.get("email"),
        "account_id": info.get("account_id"),
        "expires_in_hours": info.get("expires_in_hours"),
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
    # Validate arguments before touching auth: a typo in --days should be a
    # usage error, not a demand that you sign in first.
    days = api.parse_days(args.days)
    client = None if args.dry_run else client_from(args)
    emit(api.create_class(
        client, name=args.name, start_date=args.start, end_date=args.end,
        days=days, color=args.color,
        description=args.description or "", dry_run=args.dry_run))


def cmd_classes_update(args: argparse.Namespace) -> None:
    days = api.parse_days(args.days)
    client = None if args.dry_run else client_from(args)
    emit(api.update_class(
        client, class_id=args.class_id, name=args.name, start_date=args.start,
        end_date=args.end, days=days, color=args.color,
        description=args.description or "", dry_run=args.dry_run))


def cmd_classes_get(args: argparse.Namespace) -> None:
    emit(api.get_class(client_from(args), args.class_id))


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


def cmd_simple_read(args: argparse.Namespace) -> None:
    emit(api.simple_read(client_from(args), args.command, raw=args.raw))


def cmd_attachments(args: argparse.Namespace) -> None:
    token_info = pbtoken.describe(config.load_session())
    teacher_id = args.teacher_id or token_info.get("account_id")
    if not teacher_id:
        raise UsageError("Could not determine a teacher id; pass --teacher-id.")
    emit(api.attachments(client_from(args), teacher_id=teacher_id))


def cmd_events_list(args: argparse.Namespace) -> None:
    emit(api.list_events(client_from(args), start=args.start or "",
                         end=args.end or "", limit=args.limit,
                         search=args.search or ""))


def cmd_events_create(args: argparse.Namespace) -> None:
    client = None if args.dry_run else client_from(args)
    emit(api.create_event(client, title=args.title, date=args.date,
                          end_date=args.end_date, text=args.text or "",
                          start_time=args.start_time or "",
                          end_time=args.end_time or "",
                          private=args.private, no_school=args.no_school,
                          dry_run=args.dry_run))


def cmd_events_delete(args: argparse.Namespace) -> None:
    emit(api.delete_event(client_from(args), event_id=args.event_id,
                          dry_run=args.dry_run))


def cmd_units_list(args: argparse.Namespace) -> None:
    emit(api.list_units(client_from(args), raw=args.raw))


def cmd_units_create(args: argparse.Namespace) -> None:
    client = None if args.dry_run else client_from(args)
    emit(api.create_unit(client, class_id=args.class_id, number=args.number,
                         title=args.title, description=args.description or "",
                         start=args.start or "", end=args.end or "",
                         dry_run=args.dry_run))


def cmd_units_update(args: argparse.Namespace) -> None:
    client = None if args.dry_run else client_from(args)
    emit(api.update_unit(client, unit_id=args.unit_id, class_id=args.class_id,
                         number=args.number, title=args.title,
                         description=args.description or "",
                         start=args.start or "", end=args.end or "",
                         dry_run=args.dry_run))


def cmd_units_delete(args: argparse.Namespace) -> None:
    client = None if args.dry_run else client_from(args)
    emit(api.delete_unit(client, unit_id=args.unit_id, class_id=args.class_id,
                         dry_run=args.dry_run))


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
    # "cookie" kept as an alias: it is in older docs and in muscle memory.
    a = s_auth.add_parser(
        "import", help="read the token from a browser you are signed in to")
    a.add_argument("--browser", choices=list(browser_cookies.KNOWN_BROWSERS),
                   help="which browser to read; defaults to yours, then the rest")
    a.set_defaults(func=cmd_auth_import)
    a = s_auth.add_parser("token", aliases=["cookie"],
                          help="store an access token from a signed-in browser")
    a.add_argument("value", nargs="?",
                   help="the token, a Cookie header, or a 'Copy as cURL' paste; "
                        "prompted for (hidden) if omitted")
    a.add_argument("--no-verify", action="store_true",
                   help="store without checking the token against the API")
    a.set_defaults(func=cmd_auth_token)
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
    c.add_argument("--dry-run", action="store_true")
    c.set_defaults(func=cmd_classes_create)
    c = s_cls.add_parser("update", help="update a class (replaces its schedule)")
    c.add_argument("--class-id", dest="class_id", required=True)
    c.add_argument("--name", required=True)
    c.add_argument("--start", required=True, metavar="MM/DD/YYYY")
    c.add_argument("--end", required=True, metavar="MM/DD/YYYY")
    c.add_argument("--days", default="MTWRF")
    c.add_argument("--color", default="#7ED321")
    c.add_argument("--description")
    c.add_argument("--dry-run", action="store_true")
    c.set_defaults(func=cmd_classes_update)
    c = s_cls.add_parser("get", help="fetch one class by id")
    c.add_argument("class_id")
    c.set_defaults(func=cmd_classes_get)

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
    p_un = sub.add_parser("units", help="list, create, update and delete units")
    s_un = p_un.add_subparsers(dest="units_command", required=True)
    u = s_un.add_parser("list", help="list units")
    u.add_argument("--raw", action="store_true")
    u.set_defaults(func=cmd_units_list)
    for verb, fn in (("create", cmd_units_create), ("update", cmd_units_update)):
        u = s_un.add_parser(verb, help=f"{verb} a unit")
        if verb == "update":
            u.add_argument("--unit-id", dest="unit_id", required=True)
        u.add_argument("--class-id", dest="class_id", required=True)
        u.add_argument("--number", required=True, help="unit number, e.g. U1")
        u.add_argument("--title", required=True)
        u.add_argument("--description")
        u.add_argument("--start", metavar="MM/DD/YYYY")
        u.add_argument("--end", metavar="MM/DD/YYYY")
        u.add_argument("--dry-run", action="store_true")
        u.set_defaults(func=fn)
    u = s_un.add_parser("delete", help="delete a unit")
    u.add_argument("--unit-id", dest="unit_id", required=True)
    u.add_argument("--class-id", dest="class_id", required=True)
    u.add_argument("--dry-run", action="store_true")
    u.set_defaults(func=cmd_units_delete)

    p_ev = sub.add_parser("events", help="list, create and delete calendar events")
    s_ev = p_ev.add_subparsers(dest="events_command", required=True)
    e = s_ev.add_parser("list", help="list events")
    e.add_argument("--start", metavar="MM/DD/YYYY")
    e.add_argument("--end", metavar="MM/DD/YYYY")
    e.add_argument("--limit", type=int, default=75)
    e.add_argument("--search")
    e.set_defaults(func=cmd_events_list)
    e = s_ev.add_parser("create", help="create an event")
    e.add_argument("--title", required=True)
    e.add_argument("--date", required=True, metavar="MM/DD/YYYY")
    e.add_argument("--end-date", dest="end_date", metavar="MM/DD/YYYY",
                   help="defaults to --date")
    e.add_argument("--text", help="description; HTML accepted")
    e.add_argument("--start-time", dest="start_time")
    e.add_argument("--end-time", dest="end_time")
    e.add_argument("--private", action="store_true")
    e.add_argument("--no-school", dest="no_school", action="store_true",
                   help="mark as a no-school day")
    e.add_argument("--dry-run", action="store_true")
    e.set_defaults(func=cmd_events_create)
    e = s_ev.add_parser("delete", help="delete an event by id")
    e.add_argument("event_id")
    e.add_argument("--dry-run", action="store_true")
    e.set_defaults(func=cmd_events_delete)

    for name, (path, _unwrap) in api.SIMPLE_READS.items():
        if name in ("events", "units"):
            continue
        rp = sub.add_parser(name, help=f"read {name.replace('-', ' ')} ({path})")
        rp.add_argument("--raw", action="store_true",
                        help="print the full response envelope")
        rp.set_defaults(func=cmd_simple_read)

    p = sub.add_parser("attachments", help="list uploaded resources")
    p.add_argument("--teacher-id", dest="teacher_id",
                   help="defaults to the account id in your token")
    p.set_defaults(func=cmd_attachments)

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
