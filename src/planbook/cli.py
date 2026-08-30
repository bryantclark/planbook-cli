"""Command-line surface, aimed at agents as much as people:

* stdout carries JSON and nothing else, so it is always safe to pipe.
* Diagnostics go to stderr.
* Exit codes: 64 usage, 65 unexpected response shape, 77 not authenticated,
  1 everything else.
* Writes accept --dry-run, which prints the form payload instead of sending it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import NoReturn

import requests

from . import __version__, api, browser_cookies
from .errors import PlanbookError, UsageError
from .wire import parse_date


class _Parser(argparse.ArgumentParser):
    """Exits 64 on a bad command line, as AGENTS.md promises."""

    def error(self, message: str) -> NoReturn:  # pragma: no cover - argparse path
        self.print_usage(sys.stderr)
        print(f"error: {message}", file=sys.stderr)
        raise SystemExit(UsageError.exit_code)


def _date(value: str) -> str:
    """argparse `type` for MM/DD/YYYY, so a typo never reaches the server.

    Raises ValueError rather than UsageError because argparse catches that and
    routes it through _Parser.error, which already exits 64.
    """
    try:
        return parse_date(value)
    except UsageError as exc:
        raise ValueError(str(exc)) from None


def build_parser() -> argparse.ArgumentParser:
    from .commands.auth import (
        cmd_auth_browser,
        cmd_auth_import,
        cmd_auth_login,
        cmd_auth_logout,
        cmd_auth_status,
        cmd_auth_token,
    )
    from .commands.classes import (
        cmd_classes_create,
        cmd_classes_delete,
        cmd_classes_get,
        cmd_classes_list,
        cmd_classes_update,
    )
    from .commands.events import (
        cmd_events_create,
        cmd_events_delete,
        cmd_events_list,
    )
    from .commands.lessons import (
        cmd_lessons_bulk,
        cmd_lessons_delete,
        cmd_lessons_get,
        cmd_lessons_sections,
        cmd_lessons_set,
        cmd_lessons_week,
    )
    from .commands.misc import (
        cmd_attachments_list,
        cmd_attachments_upload,
        cmd_endpoints,
        cmd_raw,
        cmd_schedule_special_days,
        cmd_settings,
        cmd_simple_read,
        cmd_standards,
    )
    from .commands.people import (
        cmd_attendance,
        cmd_grades,
        cmd_students_create,
        cmd_students_delete,
        cmd_students_list,
        cmd_students_update,
        cmd_templates,
    )
    from .commands.todos import (
        cmd_todos_create,
        cmd_todos_delete,
        cmd_todos_list,
        cmd_todos_update,
    )
    from .commands.units import (
        cmd_units_create,
        cmd_units_delete,
        cmd_units_list,
        cmd_units_update,
    )

    parser = _Parser(
        prog="planbook",
        description="Unofficial CLI for Planbook.com. Prints JSON on stdout.",
        epilog="Docs: AGENTS.md for agent usage, docs/API-NOTES.md for the API itself.",
    )
    parser.add_argument(
        "--version", action="version", version=f"planbook-cli {__version__}"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="log each request to stderr"
    )
    parser.set_defaults(_parser_class=_Parser)
    sub = parser.add_subparsers(dest="command", required=True, parser_class=_Parser)

    p_auth = sub.add_parser("auth", help="sign in and inspect the stored session")
    s_auth = p_auth.add_subparsers(dest="auth_command", required=True)
    a = s_auth.add_parser("login", help="sign in with email and password (prompts)")
    a.add_argument("--username", help="email or user ID; prompted for if omitted")
    a.set_defaults(func=cmd_auth_login)
    a = s_auth.add_parser(
        "import", help="read the token from a browser you are signed in to"
    )
    a.add_argument(
        "--browser",
        choices=list(browser_cookies.KNOWN_BROWSERS),
        help="which browser to read; defaults to yours, then the rest",
    )
    a.set_defaults(func=cmd_auth_import)
    # "cookie" kept as an alias: it is in older docs and in muscle memory.
    a = s_auth.add_parser(
        "token",
        aliases=["cookie"],
        help="store an access token from a signed-in browser",
    )
    a.add_argument(
        "value",
        nargs="?",
        help="the token, a Cookie header, or a 'Copy as cURL' paste; "
        "prompted for (hidden) if omitted",
    )
    a.add_argument(
        "--no-verify",
        action="store_true",
        help="store without checking the token against the API",
    )
    a.set_defaults(func=cmd_auth_token)
    a = s_auth.add_parser(
        "browser", help="sign in by opening a browser (works with Google and other SSO)"
    )
    a.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="seconds to wait for sign-in (default 300)",
    )
    a.add_argument(
        "--channel",
        choices=["chrome", "msedge", "chromium"],
        help="which browser to launch; tries chrome, then edge, then chromium",
    )
    a.add_argument(
        "--profile",
        type=Path,
        help="browser profile directory (default: alongside the session file)",
    )
    a.add_argument(
        "--interactive",
        action="store_true",
        help="always open a window; skip the silent refresh attempt",
    )
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
    c.add_argument("--start", required=True, metavar="MM/DD/YYYY", type=_date)
    c.add_argument("--end", required=True, metavar="MM/DD/YYYY", type=_date)
    c.add_argument(
        "--days", default="MTWRF", help="days taught, e.g. MTWRF (R=Thursday, U=Sunday)"
    )
    c.add_argument("--color", default="#7ED321")
    c.add_argument("--description")
    c.add_argument(
        "--time",
        action="append",
        default=[],
        metavar="SPEC",
        help="class time: 9:00-9:50 for every day, or M=9:00-9:50 "
        "for one day; repeatable",
    )
    c.add_argument(
        "--lesson-layout-id",
        dest="lesson_layout_id",
        default=0,
        help="layout deciding which lesson sections exist "
        "(see `planbook lessons sections`)",
    )
    c.add_argument("--dry-run", action="store_true")
    c.set_defaults(func=cmd_classes_create)
    c = s_cls.add_parser(
        "update", help="update a class; only the fields you pass change"
    )
    c.add_argument("--class-id", dest="class_id", required=True)
    c.add_argument("--name")
    c.add_argument("--start", metavar="MM/DD/YYYY", type=_date)
    c.add_argument("--end", metavar="MM/DD/YYYY", type=_date)
    c.add_argument("--days", help="replaces the schedule, e.g. MTWRF")
    c.add_argument("--color")
    c.add_argument("--description")
    c.add_argument(
        "--time",
        action="append",
        default=[],
        metavar="SPEC",
        help="class time: 9:00-9:50 for every day in --days, or "
        "M=9:00-9:50 for one day; repeatable",
    )
    c.add_argument("--dry-run", action="store_true")
    c.set_defaults(func=cmd_classes_update)
    c = s_cls.add_parser("delete", help="delete a class AND all of its lessons")
    c.add_argument("--class-id", dest="class_id", required=True)
    c.add_argument(
        "--yes", action="store_true", help="required: confirms the lessons go too"
    )
    c.set_defaults(func=cmd_classes_delete)
    c = s_cls.add_parser("get", help="fetch one class by id")
    c.add_argument("--class-id", dest="class_id", required=True)
    c.set_defaults(func=cmd_classes_get)

    p_les = sub.add_parser("lessons", help="read and write lessons")
    s_les = p_les.add_subparsers(dest="lessons_command", required=True)
    sub_lesson = s_les.add_parser(
        "set", help="create or update one lesson (upsert by class+date)"
    )
    sub_lesson.add_argument("--class-id", dest="class_id", required=True)
    sub_lesson.add_argument("--date", required=True, metavar="MM/DD/YYYY", type=_date)
    sub_lesson.add_argument("--title")
    sub_lesson.add_argument("--text", help="lesson body; HTML is accepted")
    sub_lesson.add_argument("--homework")
    sub_lesson.add_argument("--notes")
    sub_lesson.add_argument("--unit-id", dest="unit_id")
    sub_lesson.add_argument(
        "--attach",
        action="append",
        default=[],
        metavar="FILE",
        help="attach a file: a local path is uploaded first, an "
        "existing resource name is linked; repeatable, and "
        "replaces whatever was attached",
    )
    sub_lesson.add_argument(
        "--standard",
        action="append",
        default=[],
        metavar="DB_ID",
        help="attach a standard by its db_id (see `planbook standards`); "
        "repeatable, and replaces whatever was attached",
    )
    sub_lesson.add_argument(
        "--assignment",
        action="append",
        default=[],
        metavar="ID",
        help="attach an assignment by id (see `planbook assignments`); "
        "repeatable, and replaces whatever was attached",
    )
    sub_lesson.add_argument(
        "--section",
        action="append",
        default=[],
        metavar="KEY=TEXT",
        help="write a lesson section by number (1-6) or by its label, "
        "e.g. --section 'Objectives=...'; repeatable",
    )
    sub_lesson.add_argument(
        "--dry-run",
        action="store_true",
        help="print the form payload instead of sending it",
    )
    sub_lesson.set_defaults(func=cmd_lessons_set)
    sub_lesson = s_les.add_parser("bulk", help="write many lessons from a JSON file")
    sub_lesson.add_argument(
        "file",
        help="JSON list of lesson objects; keys: "
        "class_id, date, title, text, homework, notes, "
        "unit_id, sections",
    )
    sub_lesson.add_argument(
        "--class-id", dest="class_id", help="default class_id for items that omit one"
    )
    sub_lesson.add_argument(
        "--keep-going",
        action="store_true",
        help="continue after a failed item instead of stopping",
    )
    sub_lesson.add_argument("--dry-run", action="store_true")
    sub_lesson.set_defaults(func=cmd_lessons_bulk)
    sub_lesson = s_les.add_parser(
        "sections",
        help="show the six lesson sections, their labels and whether they are on",
    )
    sub_lesson.set_defaults(func=cmd_lessons_sections)
    sub_lesson = s_les.add_parser("get", help="read one saved lesson")
    sub_lesson.add_argument("--class-id", dest="class_id", required=True)
    sub_lesson.add_argument("--date", required=True, metavar="MM/DD/YYYY", type=_date)
    sub_lesson.set_defaults(func=cmd_lessons_get)
    sub_lesson = s_les.add_parser("delete", help="clear the lesson on one date")
    sub_lesson.add_argument("--class-id", dest="class_id", required=True)
    sub_lesson.add_argument("--date", required=True, metavar="MM/DD/YYYY", type=_date)
    sub_lesson.add_argument("--dry-run", action="store_true")
    sub_lesson.set_defaults(func=cmd_lessons_delete)
    sub_lesson = s_les.add_parser(
        "week", help="fetch a week of lessons and events (partial mapping)"
    )
    sub_lesson.add_argument("--monday", required=True, metavar="MM/DD/YYYY", type=_date)
    sub_lesson.add_argument("--weeks", type=int, default=1)
    sub_lesson.add_argument(
        "--all", action="store_true", help="include days with no saved lesson"
    )
    sub_lesson.add_argument(
        "--raw", action="store_true", help="print the unmapped response body"
    )
    sub_lesson.set_defaults(func=cmd_lessons_week)

    p_sch = sub.add_parser("schedule", help="school calendar")
    s_sch = p_sch.add_subparsers(dest="schedule_command", required=True)
    s = s_sch.add_parser("special-days", help="holidays and non-teaching days")
    s.add_argument("--teacher-id", dest="teacher_id", help="default: from the token")
    s.add_argument("--year-id", dest="year_id", help="default: from the token")
    s.add_argument("--school-id", dest="school_id", default=0)
    s.set_defaults(func=cmd_schedule_special_days)

    p = sub.add_parser("settings", help="account settings")
    p.set_defaults(func=cmd_settings)
    p = sub.add_parser("standards", help="standards available to the account")
    p.add_argument("--search", help="filter by standard id or description text")
    p.add_argument("--raw", action="store_true")
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
        t.add_argument("--start", required=True, metavar="MM/DD/YYYY", type=_date)
        t.add_argument(
            "--due", metavar="MM/DD/YYYY", type=_date, help="defaults to --start"
        )
        t.add_argument("--priority", choices=["low", "medium", "high"], default="low")
        t.add_argument("--done", action="store_true")
        t.add_argument("--repeats", default="daily")
        t.set_defaults(func=fn)
    t = s_td.add_parser("delete", help="delete a to-do")
    t.add_argument("--todo-id", dest="todo_id", required=True)
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
        u.add_argument("--start", metavar="MM/DD/YYYY", type=_date)
        u.add_argument("--end", metavar="MM/DD/YYYY", type=_date)
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
    e.add_argument("--start", metavar="MM/DD/YYYY", type=_date)
    e.add_argument("--end", metavar="MM/DD/YYYY", type=_date)
    e.add_argument("--limit", type=int, default=75)
    e.add_argument("--search")
    e.set_defaults(func=cmd_events_list)
    e = s_ev.add_parser("create", help="create an event")
    e.add_argument("--title", required=True)
    e.add_argument("--date", required=True, metavar="MM/DD/YYYY", type=_date)
    e.add_argument(
        "--end-date",
        dest="end_date",
        metavar="MM/DD/YYYY",
        type=_date,
        help="defaults to --date",
    )
    e.add_argument("--text", help="description; HTML accepted")
    e.add_argument("--start-time", dest="start_time")
    e.add_argument("--end-time", dest="end_time")
    e.add_argument("--private", action="store_true")
    e.add_argument(
        "--no-school",
        dest="no_school",
        action="store_true",
        help="mark as a no-school day",
    )
    e.add_argument(
        "--force",
        action="store_true",
        help="with --no-school, delete the lessons that already exist on that date",
    )
    e.add_argument(
        "--repeats",
        default="daily",
        help="recurrence across the date range (default: daily)",
    )
    e.add_argument("--dry-run", action="store_true")
    e.set_defaults(func=cmd_events_create)
    e = s_ev.add_parser(
        "delete", help="delete an event by id (the whole series by default)"
    )
    e.add_argument("--event-id", dest="event_id", required=True)
    e.add_argument(
        "--occurrence-only",
        dest="occurrence_only",
        action="store_true",
        help="delete only this date, not the whole repeating series",
    )
    e.add_argument("--dry-run", action="store_true")
    e.set_defaults(func=cmd_events_delete)

    p_st = sub.add_parser("students", help="list, create, update and delete students")
    s_st = p_st.add_subparsers(dest="students_command", required=True)
    st = s_st.add_parser("list", help="students in a class, or all of them")
    st.add_argument(
        "--class-id", dest="class_id", help="omit for every student on the account"
    )
    st.set_defaults(func=cmd_students_list)
    for verb, fn in (("create", cmd_students_create), ("update", cmd_students_update)):
        st = s_st.add_parser(verb, help=f"{verb} a student")
        if verb == "update":
            st.add_argument("--student-id", dest="student_id", required=True)
        st.add_argument("--first-name", dest="first_name", required=True)
        st.add_argument("--last-name", dest="last_name", required=True)
        st.add_argument("--middle-name", dest="middle_name")
        st.add_argument("--code", help="student id/code used by the school")
        st.add_argument("--email")
        st.add_argument("--parent-email", dest="parent_email")
        st.add_argument("--phone")
        st.add_argument("--birthdate", metavar="MM/DD/YYYY", type=_date)
        st.set_defaults(func=fn)
    st = s_st.add_parser("delete", help="delete a student")
    st.add_argument("--student-id", dest="student_id", required=True)
    st.set_defaults(func=cmd_students_delete)

    p = sub.add_parser("attendance", help="read attendance for a class on a date")
    p.add_argument("--class-id", dest="class_id", required=True)
    p.add_argument("--date", required=True, metavar="MM/DD/YYYY", type=_date)
    p.set_defaults(func=cmd_attendance)

    p = sub.add_parser("grades", help="grade periods and scored assignments")
    p.add_argument("--class-id", dest="class_id", required=True)
    p.set_defaults(func=cmd_grades)

    p = sub.add_parser("templates", help="lesson templates")
    p.add_argument("--teacher-id", dest="teacher_id")
    p.set_defaults(func=cmd_templates)

    for name, (path, _unwrap) in api.SIMPLE_READS.items():
        if name in ("events", "units", "todos", "students"):
            continue
        rp = sub.add_parser(name, help=f"read {name.replace('-', ' ')} ({path})")
        rp.add_argument(
            "--raw", action="store_true", help="print the full response envelope"
        )
        rp.set_defaults(func=cmd_simple_read)

    p_at = sub.add_parser("attachments", help="upload and list resource files")
    s_at = p_at.add_subparsers(dest="attachments_command", required=True)
    a = s_at.add_parser("list", help="list uploaded resources")
    a.add_argument(
        "--teacher-id",
        dest="teacher_id",
        help="defaults to the account id in your token",
    )
    a.set_defaults(func=cmd_attachments_list)
    a = s_at.add_parser("upload", help="upload one or more files")
    a.add_argument("files", nargs="+", help="local file paths")
    a.set_defaults(func=cmd_attachments_upload)

    p = sub.add_parser(
        "endpoints", help="list known API endpoints and how well they are mapped"
    )
    p.set_defaults(func=cmd_endpoints)

    p = sub.add_parser(
        "raw", help="POST to any endpoint (escape hatch for unmapped calls)"
    )
    p.add_argument("path", help="endpoint path, e.g. /getAssignments")
    p.add_argument(
        "-F",
        "--field",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="form field; repeatable",
    )
    p.add_argument(
        "--get",
        action="store_true",
        help="send as GET; some /services/planbook/** endpoints are GET-only "
        "and answer a POST with 405",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="send fields as a JSON body; a few service endpoints reject form "
        "encoding with \"A JSONObject text must begin with '{'\"",
    )
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
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return PlanbookError.exit_code
    except requests.RequestException as exc:
        print(f"error: could not reach Planbook: {exc}", file=sys.stderr)
        return PlanbookError.exit_code
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
