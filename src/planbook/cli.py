"""Command-line surface, aimed at agents as much as people:

* stdout carries JSON and nothing else, so it is always safe to pipe.
* Diagnostics go to stderr.
* Exit codes: 64 usage, 65 unexpected response shape, 77 not authenticated,
  1 everything else.
* Writes accept --dry-run, which prints the form payload instead of sending it.
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path
from typing import Any

import requests

import os

from . import __version__, api, auth, browser_auth, config
from . import browser_cookies
from . import token as pbtoken
from .client import PlanbookClient
from .endpoints import ENDPOINTS
from .errors import NotAuthenticated, PlanbookError, UsageError


def emit(value: Any) -> None:
    json.dump(value, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")


def client_from(args: argparse.Namespace) -> PlanbookClient:
    return PlanbookClient(config.load_session(), verbose=args.verbose)


def cmd_auth_login(args: argparse.Namespace) -> None:
    username = args.username or input("Email or user ID: ").strip()
    # Read from the TTY: never logged, never in argv, never stored.
    password = getpass.getpass("Password: ")
    cookie = auth.login(username, password)
    path = config.save_session(cookie, username)
    emit({"ok": True, "stored": str(path), "username": username})


def cmd_auth_token(args: argparse.Namespace) -> None:
    """Store a Planbook access token copied out of a signed-in browser.

    Accepts a bare JWT, a Cookie header, or a "Copy as cURL" paste. Verifies
    first, so a bad token fails here rather than three commands later.
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

    The recommended path: nothing is automated and nothing is copied by hand.
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
        except NotAuthenticated:
            continue  # stale token from an old sign-in; try the next browser
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

    Discouraged (see README), but kept: it needs no manual copying, and would
    become the good path if Planbook ever registered an OAuth client.
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


def cmd_classes_list(args: argparse.Namespace) -> None:
    emit(api.list_classes(client_from(args), raw=args.raw))


def cmd_classes_create(args: argparse.Namespace) -> None:
    # Validate before touching auth: a typo in --days should be a usage error,
    # not a demand that you sign in first.
    days = api.parse_days(args.days)
    client = None if args.dry_run else client_from(args)
    emit(api.create_class(
        client, name=args.name, start_date=args.start, end_date=args.end,
        days=days, color=args.color, description=args.description or "",
        times=api.parse_day_times(args.time, days),
        lesson_layout_id=args.lesson_layout_id, dry_run=args.dry_run))


def cmd_classes_update(args: argparse.Namespace) -> None:
    days = api.parse_days(args.days) if args.days else None
    if args.time and any("=" not in spec for spec in args.time) and days is None:
        raise UsageError(
            "A bare --time needs --days to know which days it applies to. "
            "Use --time M=9:00-9:50 to set one day without changing the schedule."
        )
    emit(api.update_class(
        client_from(args), class_id=args.class_id, name=args.name,
        start_date=args.start, end_date=args.end, days=days,
        color=args.color, description=args.description,
        times=api.parse_day_times(args.time, days) if args.time else None,
        dry_run=args.dry_run))


def cmd_classes_get(args: argparse.Namespace) -> None:
    emit(api.get_class(client_from(args), args.class_id))


def _sections_from(args: argparse.Namespace, client) -> dict[int, str] | None:
    """Resolve --section SPEC values to section indexes.

    Labels come from the account's lesson layout, so this only fetches
    settings when a label (rather than a number) is actually used.
    """
    if not args.section:
        return None
    resolved: dict[int, str] = {}
    known = None
    for spec in args.section:
        key, sep, value = spec.partition("=")
        if not sep:
            raise UsageError(
                f"--section {spec!r} needs KEY=TEXT, e.g. 4=... or Homework=..."
            )
        if not key.strip().isdigit() and known is None:
            known = api.lesson_sections(client or client_from(args))
        resolved[api.resolve_section(known or [], key)] = value
    return resolved


def cmd_lessons_sections(args: argparse.Namespace) -> None:
    emit(api.lesson_sections(client_from(args)))


def cmd_lessons_set(args: argparse.Namespace) -> None:
    # A dry run must not need a session; it is the safe first step.
    client = None if args.dry_run else client_from(args)
    if client is not None and args.date in api.no_school_dates(client):
        print(f"warning: {args.date} is marked as a no-school day.",
              file=sys.stderr)
    emit(api.set_lesson(
        client,
        class_id=args.class_id,
        date=args.date,
        title=args.title,
        text=args.text,
        homework=args.homework,
        notes=args.notes,
        unit_id=args.unit_id,
        start_time=args.start_time,
        end_time=args.end_time,
        sections=_sections_from(args, client),
        dry_run=args.dry_run,
    ))


def _require_class_id(item: dict, args: argparse.Namespace, index: int) -> Any:
    """A missing class id is a user error, not a zero.

    `intish` turns absent integers into "0" because that is what the API
    wants for genuinely optional ids. Letting that default through here
    would post lessons to class 0.
    """
    class_id = item.get("class_id", args.class_id)
    if class_id in (None, ""):
        raise UsageError(
            f"Item {index} has no class_id and --class-id was not given."
        )
    return class_id


BULK_KEYS = {"class_id", "date", "title", "text", "homework", "notes",
             "unit_id", "start_time", "end_time", "sections"}


def _bulk_sections(item: dict, args: argparse.Namespace, index: int):
    """Read a bulk item's `sections` map, resolving labels the same as --section."""
    raw = item.get("sections")
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise UsageError(f"Item {index}: `sections` must be an object.")
    known = None
    resolved = {}
    for key, value in raw.items():
        if not str(key).strip().isdigit() and known is None:
            known = api.lesson_sections(client_from(args))
        resolved[api.resolve_section(known or [], str(key))] = value
    return resolved


def cmd_lessons_bulk(args: argparse.Namespace) -> None:
    """Write many lessons from a JSON file.

    A list of objects taking the same keys as `lessons set`. Sent one at a
    time, in order, on purpose: this is somebody's real planbook.
    """
    try:
        items = json.loads(open(args.file).read())
    except (OSError, ValueError) as exc:
        raise UsageError(f"Could not read {args.file}: {exc}") from exc
    if not isinstance(items, list):
        raise UsageError(f"{args.file} must contain a JSON list of lesson objects.")

    # Validate everything before writing anything: a typo in item 40 should
    # not leave 39 lessons half-applied.
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise UsageError(f"Item {index} is not an object.")
        if "date" not in item:
            raise UsageError(f"Item {index} is missing 'date'.")
        unknown = set(item) - BULK_KEYS
        if unknown:
            raise UsageError(
                f"Item {index} has unknown key(s): {', '.join(sorted(unknown))}. "
                f"Accepted: {', '.join(sorted(BULK_KEYS))}."
            )
        _require_class_id(item, args, index)

    client = None if args.dry_run else client_from(args)
    if client is not None:
        closed = api.no_school_dates(client)
        hit = sorted({i["date"] for i in items if i.get("date") in closed})
        if hit:
            print(f"warning: no-school day(s) in this batch: {', '.join(hit)}",
                  file=sys.stderr)
    results, failures = [], 0
    for index, item in enumerate(items):
        try:
            results.append(api.set_lesson(
                client,
                class_id=_require_class_id(item, args, index),
                date=item["date"],
                title=item.get("title"),
                text=item.get("text"),
                homework=item.get("homework"),
                notes=item.get("notes"),
                unit_id=item.get("unit_id"),
                start_time=item.get("start_time"),
                end_time=item.get("end_time"),
                sections=_bulk_sections(item, args, index),
                dry_run=args.dry_run,
            ))
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
                          repeats=args.repeats, dry_run=args.dry_run))


def cmd_events_delete(args: argparse.Namespace) -> None:
    emit(api.delete_event(client_from(args), event_id=args.event_id,
                          occurrence_only=args.occurrence_only,
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


def cmd_classes_delete(args: argparse.Namespace) -> None:
    if not args.yes:
        raise UsageError(
            "Deleting a class also deletes every lesson in it, permanently. "
            "Pass --yes to confirm."
        )
    emit(api.delete_class(client_from(args), class_id=args.class_id))


def cmd_lessons_delete(args: argparse.Namespace) -> None:
    client = None if args.dry_run else client_from(args)
    emit(api.delete_lesson(client, class_id=args.class_id, date=args.date,
                           dry_run=args.dry_run))


def cmd_todos_list(args: argparse.Namespace) -> None:
    emit(api.list_todos(client_from(args), class_id=args.class_id or "all"))


def cmd_todos_create(args: argparse.Namespace) -> None:
    emit(api.create_todo(client_from(args), text=args.text, start=args.start,
                         due=args.due or "", priority=args.priority,
                         done=args.done, repeats=args.repeats))


def cmd_todos_update(args: argparse.Namespace) -> None:
    emit(api.update_todo(client_from(args), todo_id=args.todo_id, text=args.text,
                         start=args.start, due=args.due or "",
                         priority=args.priority, done=args.done,
                         repeats=args.repeats))


def cmd_todos_delete(args: argparse.Namespace) -> None:
    emit(api.delete_todo(client_from(args), todo_id=args.todo_id))


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


class _Parser(argparse.ArgumentParser):
    """Exits 64 on a bad command line, as AGENTS.md promises."""

    def error(self, message: str) -> None:  # pragma: no cover - argparse path
        self.print_usage(sys.stderr)
        print(f"error: {message}", file=sys.stderr)
        raise SystemExit(UsageError.exit_code)


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="planbook",
        description="Unofficial CLI for Planbook.com. Prints JSON on stdout.",
        epilog="Docs: AGENTS.md for agent usage, docs/API-NOTES.md for the API itself.",
    )
    parser.add_argument("--version", action="version", version=f"planbook-cli {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="log each request to stderr")
    parser.set_defaults(_parser_class=_Parser)
    sub = parser.add_subparsers(dest="command", required=True,
                                parser_class=_Parser)

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
    c.add_argument("--time", action="append", default=[], metavar="SPEC",
                   help="class time: 9:00-9:50 for every day, or M=9:00-9:50 "
                        "for one day; repeatable")
    c.add_argument("--lesson-layout-id", dest="lesson_layout_id", default=0,
                   help="layout deciding which lesson sections exist "
                        "(see `planbook lessons sections`)")
    c.add_argument("--dry-run", action="store_true")
    c.set_defaults(func=cmd_classes_create)
    c = s_cls.add_parser(
        "update",
        help="update a class; only the fields you pass change")
    c.add_argument("--class-id", dest="class_id", required=True)
    c.add_argument("--name")
    c.add_argument("--start", metavar="MM/DD/YYYY")
    c.add_argument("--end", metavar="MM/DD/YYYY")
    c.add_argument("--days", help="replaces the schedule, e.g. MTWRF")
    c.add_argument("--color")
    c.add_argument("--description")
    c.add_argument("--time", action="append", default=[], metavar="SPEC",
                   help="class time: 9:00-9:50 for every day in --days, or "
                        "M=9:00-9:50 for one day; repeatable")
    c.add_argument("--dry-run", action="store_true")
    c.set_defaults(func=cmd_classes_update)
    c = s_cls.add_parser("delete", help="delete a class AND all of its lessons")
    c.add_argument("class_id")
    c.add_argument("--yes", action="store_true",
                   help="required: confirms the lessons go too")
    c.set_defaults(func=cmd_classes_delete)
    c = s_cls.add_parser("get", help="fetch one class by id")
    c.add_argument("class_id")
    c.set_defaults(func=cmd_classes_get)

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
    l.add_argument("--start-time", dest="start_time", metavar="TIME",
                   help="lesson start, e.g. 9:00am or 14:30")
    l.add_argument("--end-time", dest="end_time", metavar="TIME")
    l.add_argument("--section", action="append", default=[], metavar="KEY=TEXT",
                   help="write a lesson section by number (1-6) or by its label, "
                        "e.g. --section 'Objectives=...'; repeatable")
    l.add_argument("--dry-run", action="store_true",
                   help="print the form payload instead of sending it")
    l.set_defaults(func=cmd_lessons_set)
    l = s_les.add_parser("bulk", help="write many lessons from a JSON file")
    l.add_argument("file",
                   help="JSON list of lesson objects; keys: "
                        "class_id, date, title, text, homework, notes, "
                        "unit_id, start_time, end_time, sections")
    l.add_argument("--class-id", dest="class_id",
                   help="default class_id for items that omit one")
    l.add_argument("--keep-going", action="store_true",
                   help="continue after a failed item instead of stopping")
    l.add_argument("--dry-run", action="store_true")
    l.set_defaults(func=cmd_lessons_bulk)
    l = s_les.add_parser(
        "sections",
        help="show the six lesson sections, their labels and whether they are on")
    l.set_defaults(func=cmd_lessons_sections)
    l = s_les.add_parser("delete", help="clear the lesson on one date")
    l.add_argument("--class-id", dest="class_id", required=True)
    l.add_argument("--date", required=True, metavar="MM/DD/YYYY")
    l.add_argument("--dry-run", action="store_true")
    l.set_defaults(func=cmd_lessons_delete)
    l = s_les.add_parser("week", help="fetch a week of lessons and events (partial mapping)")
    l.add_argument("--monday", required=True, metavar="MM/DD/YYYY")
    l.add_argument("--weeks", type=int, default=1)
    l.set_defaults(func=cmd_lessons_week)

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
    p_td = sub.add_parser("todos", help="list, create, update and delete to-dos")
    s_td = p_td.add_subparsers(dest="todos_command", required=True)
    t = s_td.add_parser("list", help="list to-dos")
    t.add_argument("--class-id", dest="class_id", help="defaults to all classes")
    t.set_defaults(func=cmd_todos_list)
    for verb, fn in (("create", cmd_todos_create), ("update", cmd_todos_update)):
        t = s_td.add_parser(verb, help=f"{verb} a to-do")
        if verb == "update":
            t.add_argument("--todo-id", dest="todo_id", required=True)
        t.add_argument("--text", required=True, help="HTML accepted")
        t.add_argument("--start", required=True, metavar="MM/DD/YYYY")
        t.add_argument("--due", metavar="MM/DD/YYYY", help="defaults to --start")
        t.add_argument("--priority", choices=["low", "medium", "high"],
                       default="low")
        t.add_argument("--done", action="store_true")
        t.add_argument("--repeats", default="daily")
        t.set_defaults(func=fn)
    t = s_td.add_parser("delete", help="delete a to-do")
    t.add_argument("todo_id")
    t.set_defaults(func=cmd_todos_delete)

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
    e.add_argument("--repeats", default="daily",
                   help="recurrence across the date range (default: daily)")
    e.add_argument("--dry-run", action="store_true")
    e.set_defaults(func=cmd_events_create)
    e = s_ev.add_parser(
        "delete", help="delete an event by id (the whole series by default)")
    e.add_argument("event_id")
    e.add_argument("--occurrence-only", dest="occurrence_only",
                   action="store_true",
                   help="delete only this date, not the whole repeating series")
    e.add_argument("--dry-run", action="store_true")
    e.set_defaults(func=cmd_events_delete)

    for name, (path, _unwrap) in api.SIMPLE_READS.items():
        if name in ("events", "units", "todos"):
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
    except ValueError as exc:
        # int() on a non-numeric --class-id and friends. AGENTS.md promises
        # 64 for bad arguments, not a traceback.
        print(f"error: invalid argument: {exc}", file=sys.stderr)
        return UsageError.exit_code
    except requests.RequestException as exc:
        print(f"error: could not reach Planbook: {exc}", file=sys.stderr)
        return PlanbookError.exit_code
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
