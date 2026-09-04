"""Command-line surface, aimed at agents as much as people:

* stdout carries JSON on success and is empty on failure; diagnostics go to
  stderr. Branch on the exit code before parsing stdout.
* Exit codes: 64 usage, 65 unexpected response shape, 77 not authenticated,
  1 everything else.
* `--error-json` turns the stderr diagnostic into one JSON object carrying a
  kind, a code, a retryable flag and a remedy, so nothing has to parse prose.
* Writes accept --dry-run, which prints the exact request instead of sending
  it. It still reads, so it needs a session.
* `planbook schema` dumps this whole surface as JSON; `planbook check` is the
  one-call preflight (auth + token life + class ids).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import NoReturn

import requests

from . import __version__, browser_cookies
from .contract import CONTRACT_VERSION
from .errors import PlanbookError, TransportError, UsageError
from .resources.misc import SIMPLE_READS
from .wire import parse_date

STDIN_HELP = "pass `-` to read this value from stdin, which avoids quoting HTML"


def stdin_flags(parser: argparse.ArgumentParser, *dests: str) -> None:
    """Declare which arguments accept `-`, for `planbook schema`.

    Sniffing the help text for this drifted in both directions: a flag whose
    prose said `-` but whose command never read stdin published a write flag
    that stores a literal dash.
    """
    parser.planbook_stdin = dests  # type: ignore[attr-defined]


def marks(parser: argparse.ArgumentParser, *names: str) -> None:
    """Declare what a command does, for `planbook schema`.

    `writes` changes the account; `destructive` also removes something that
    cannot be restored. Inferring either from the name would miss `raw`.
    """
    existing = getattr(parser, "planbook_marks", ())
    # Accumulate: assigning would let a second call silently erase the first.
    parser.planbook_marks = (*existing, *names)  # type: ignore[attr-defined]


def _dry_run(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the exact request(s) as JSON instead of sending them. "
        "Sends no write, but reads what it needs for an accurate preview, so "
        "it needs a session",
    )


def _yes(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--yes",
        action="store_true",
        help="confirm a delete that also destroys records you did not name",
    )


def _id_only(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--id-only",
        dest="id_only",
        action="store_true",
        help='print only {"id": N}, so a chained write needs no second lookup',
    )


def _raw(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--raw", action="store_true", help="print the unmapped wire format"
    )


def _class_id(parser: argparse.ArgumentParser, **kwargs: object) -> None:
    parser.add_argument("--class-id", dest="class_id", **kwargs)  # type: ignore[arg-type]


def _date_arg(parser: argparse.ArgumentParser, flag: str, **kwargs: object) -> None:
    parser.add_argument(flag, metavar="MM/DD/YYYY", type=_date, **kwargs)  # type: ignore[arg-type]


class _Parser(argparse.ArgumentParser):
    """Exits 64 on a bad command line, as AGENTS.md promises."""

    def error(self, message: str) -> NoReturn:  # pragma: no cover - argparse path
        self.print_usage(sys.stderr)
        print(f"error: {message}", file=sys.stderr)
        raise SystemExit(UsageError.exit_code)


def _date(value: str) -> str:
    """argparse `type` for MM/DD/YYYY, so a typo never reaches the server.

    Raises ValueError: argparse routes that through _Parser.error, which exits 64.
    """
    try:
        return parse_date(value)
    except UsageError as exc:
        raise ValueError(str(exc)) from None


def build_parser() -> argparse.ArgumentParser:
    from .commands.auth import (
        cmd_auth_import,
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
    from .commands.meta import cmd_check, cmd_endpoints, cmd_schema
    from .commands.misc import (
        cmd_attachments_list,
        cmd_attachments_upload,
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
    parser.add_argument(
        "--error-json",
        dest="error_json",
        action="store_true",
        default=bool(os.environ.get("PLANBOOK_ERROR_JSON")),
        help="on failure print one JSON error object on stderr instead of a "
        "sentence (or set PLANBOOK_ERROR_JSON=1)",
    )
    parser.set_defaults(_parser_class=_Parser)
    sub = parser.add_subparsers(dest="command", required=True, parser_class=_Parser)

    p_auth = sub.add_parser("auth", help="sign in and inspect the stored session")
    s_auth = p_auth.add_subparsers(dest="auth_command", required=True)
    a = s_auth.add_parser(
        "import", help="read the token from a browser you are signed in to"
    )
    a.add_argument(
        "--browser",
        choices=list(browser_cookies.KNOWN_BROWSERS),
        help="which browser to read; defaults to yours, then the rest",
    )
    a.add_argument(
        "--no-wait",
        action="store_true",
        help="do not open the sign-in page and wait; fail if no token is found",
    )
    a.add_argument(
        "--wait-timeout",
        dest="wait_timeout",
        type=int,
        default=180,
        help="seconds to wait for you to sign in (default 180)",
    )
    marks(a, "writes")
    a.set_defaults(func=cmd_auth_import)
    a = s_auth.add_parser(
        "token", help="store an access token from a signed-in browser"
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
    marks(a, "writes")
    a.set_defaults(func=cmd_auth_token)
    a = s_auth.add_parser("status", help="verify the stored session works")
    a.set_defaults(func=cmd_auth_status)
    a = s_auth.add_parser("logout", help="delete the stored session")
    marks(a, "writes")
    a.set_defaults(func=cmd_auth_logout)

    p_cls = sub.add_parser("classes", help="list and create classes")
    s_cls = p_cls.add_subparsers(dest="classes_command", required=True)
    c = s_cls.add_parser("list", help="list classes with their weekly schedule")
    _raw(c)
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
    _dry_run(c)
    _id_only(c)
    marks(c, "writes")
    c.set_defaults(func=cmd_classes_create)
    c = s_cls.add_parser(
        "update", help="update a class; only the fields you pass change"
    )
    _class_id(c, required=True)
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
    _dry_run(c)
    marks(c, "writes")
    c.set_defaults(func=cmd_classes_update)
    c = s_cls.add_parser("delete", help="delete a class AND all of its lessons")
    _class_id(c, required=True)
    _dry_run(c)
    c.add_argument(
        "--yes", action="store_true", help="required: confirms the lessons go too"
    )
    marks(c, "writes", "destructive")
    c.set_defaults(func=cmd_classes_delete)
    c = s_cls.add_parser("get", help="fetch one class by id")
    _class_id(c, required=True)
    c.set_defaults(func=cmd_classes_get)

    p_les = sub.add_parser("lessons", help="read and write lessons")
    s_les = p_les.add_subparsers(dest="lessons_command", required=True)
    sub_lesson = s_les.add_parser(
        "set", help="create or update one lesson (upsert by class+date)"
    )
    _class_id(sub_lesson, required=True)
    _date_arg(sub_lesson, "--date", required=True)
    sub_lesson.add_argument("--title", help=STDIN_HELP)
    sub_lesson.add_argument(
        "--text", help="lesson body; HTML is accepted. " + STDIN_HELP
    )
    sub_lesson.add_argument("--homework", help=STDIN_HELP)
    sub_lesson.add_argument("--notes", help=STDIN_HELP)
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
        "e.g. --section 'Objectives=...'; repeatable. "
        "KEY=- reads the text from stdin",
    )
    _dry_run(sub_lesson)
    stdin_flags(sub_lesson, "title", "text", "homework", "notes", "section")
    marks(sub_lesson, "writes")
    sub_lesson.set_defaults(func=cmd_lessons_set)
    sub_lesson = s_les.add_parser("bulk", help="write many lessons from a JSON file")
    sub_lesson.add_argument(
        "file",
        help="JSON list of lesson objects; keys: "
        "class_id, date, title, text, homework, notes, "
        "unit_id, sections. `-` reads the list from stdin",
    )
    sub_lesson.add_argument(
        "--journal",
        metavar="PATH",
        help="record every item as it lands, so an interrupted run can be "
        "resumed without rewriting what already went through",
    )
    sub_lesson.add_argument(
        "--resume",
        action="store_true",
        help="with --journal, skip items that journal shows already written "
        "with the same content",
    )
    _class_id(sub_lesson, help="default class_id for items that omit one")
    sub_lesson.add_argument(
        "--keep-going",
        action="store_true",
        help="continue after a failed item instead of stopping",
    )
    _dry_run(sub_lesson)
    stdin_flags(sub_lesson, "file")
    marks(sub_lesson, "writes")
    sub_lesson.set_defaults(func=cmd_lessons_bulk)
    sub_lesson = s_les.add_parser(
        "sections",
        help="show the six lesson sections, their labels and whether they are on",
    )
    sub_lesson.set_defaults(func=cmd_lessons_sections)
    sub_lesson = s_les.add_parser("get", help="read one saved lesson")
    _class_id(sub_lesson, required=True)
    _date_arg(sub_lesson, "--date", required=True)
    sub_lesson.add_argument(
        "--raw", action="store_true", help="the untouched wire record"
    )
    sub_lesson.set_defaults(func=cmd_lessons_get)
    sub_lesson = s_les.add_parser("delete", help="clear the lesson on one date")
    _class_id(sub_lesson, required=True)
    _date_arg(sub_lesson, "--date", required=True)
    _dry_run(sub_lesson)
    marks(sub_lesson, "writes", "destructive")
    sub_lesson.set_defaults(func=cmd_lessons_delete)
    sub_lesson = s_les.add_parser("week", help="a week of lessons grouped by date")
    sub_lesson.add_argument(
        "--monday",
        required=True,
        metavar="MM/DD/YYYY",
        type=_date,
        help="any date in the week; the range starts on its Sunday",
    )
    sub_lesson.add_argument(
        "--weeks", type=int, default=1, help="how many weeks to return (default 1)"
    )
    sub_lesson.add_argument(
        "--all",
        action="store_true",
        help="include class slots on a day that have no saved lesson",
    )
    sub_lesson.add_argument(
        "--raw",
        action="store_true",
        help="the undecoded body; the only form that also carries calendar events",
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
    _raw(p)
    p.set_defaults(func=cmd_standards)
    p_td = sub.add_parser("todos", help="list, create, update and delete to-dos")
    s_td = p_td.add_subparsers(dest="todos_command", required=True)
    t = s_td.add_parser("list", help="list to-dos")
    _class_id(t, help="defaults to all classes")
    _raw(t)
    t.set_defaults(func=cmd_todos_list)
    for verb, fn in (("create", cmd_todos_create), ("update", cmd_todos_update)):
        t = s_td.add_parser(verb, help=f"{verb} a to-do")
        creating = verb == "create"
        # On update, unnamed fields are carried over, so a default would
        # overwrite them: the callback must see None.
        if not creating:
            t.add_argument("--todo-id", dest="todo_id", required=True)
        t.add_argument("--text", required=creating, help="HTML accepted. " + STDIN_HELP)
        t.add_argument("--start", required=creating, metavar="MM/DD/YYYY", type=_date)
        t.add_argument(
            "--due", metavar="MM/DD/YYYY", type=_date, help="defaults to --start"
        )
        t.add_argument(
            "--priority",
            choices=["low", "medium", "high"],
            default="low" if creating else None,
        )
        t.add_argument(
            "--done",
            action="store_const",
            const=True,
            default=False if creating else None,
        )
        if not creating:
            t.add_argument(
                "--not-done",
                dest="done",
                action="store_const",
                const=False,
                help="mark a completed to-do as not done",
            )
        t.add_argument(
            "--repeats",
            default="daily" if creating else None,
            help="recurrence; defaults to 'daily' on create, so a one-off "
            "to-do needs an explicit non-repeating value",
        )
        _dry_run(t)
        if creating:
            _id_only(t)
        stdin_flags(t, "text")
        marks(t, "writes")
        t.set_defaults(func=fn)
    t = s_td.add_parser("delete", help="delete a to-do")
    t.add_argument("--todo-id", dest="todo_id", required=True)
    _dry_run(t)
    marks(t, "writes", "destructive")
    t.set_defaults(func=cmd_todos_delete)

    p_un = sub.add_parser("units", help="list, create, update and delete units")
    s_un = p_un.add_subparsers(dest="units_command", required=True)
    u = s_un.add_parser("list", help="list units")
    _raw(u)
    u.set_defaults(func=cmd_units_list)
    for verb, fn in (("create", cmd_units_create), ("update", cmd_units_update)):
        u = s_un.add_parser(verb, help=f"{verb} a unit")
        creating = verb == "create"
        # On update, unnamed fields are carried over, so a default would
        # overwrite them: the callback must see None.
        if not creating:
            u.add_argument("--unit-id", dest="unit_id", required=True)
        _class_id(u, required=True)
        u.add_argument("--number", required=creating, help="unit number, e.g. U1")
        u.add_argument("--title", required=creating)
        u.add_argument("--description")
        u.add_argument("--start", metavar="MM/DD/YYYY", type=_date)
        u.add_argument("--end", metavar="MM/DD/YYYY", type=_date)
        _dry_run(u)
        if creating:
            _id_only(u)
        marks(u, "writes")
        u.set_defaults(func=fn)
    u = s_un.add_parser("delete", help="delete a unit")
    u.add_argument("--unit-id", dest="unit_id", required=True)
    _class_id(u, required=True)
    _dry_run(u)
    marks(u, "writes", "destructive")
    u.set_defaults(func=cmd_units_delete)

    p_ev = sub.add_parser("events", help="list, create and delete calendar events")
    s_ev = p_ev.add_subparsers(dest="events_command", required=True)
    e = s_ev.add_parser("list", help="list events")
    e.add_argument("--start", metavar="MM/DD/YYYY", type=_date)
    e.add_argument("--end", metavar="MM/DD/YYYY", type=_date)
    e.add_argument("--limit", type=int, default=75)
    e.add_argument("--search")
    _raw(e)
    e.set_defaults(func=cmd_events_list)
    e = s_ev.add_parser("create", help="create an event")
    e.add_argument("--title", required=True)
    _date_arg(e, "--date", required=True)
    e.add_argument(
        "--end-date",
        dest="end_date",
        metavar="MM/DD/YYYY",
        type=_date,
        help="defaults to --date",
    )
    e.add_argument("--text", help="description; HTML accepted. " + STDIN_HELP)
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
        "--yes",
        action="store_true",
        help="with --no-school, confirm deleting the lessons already on those dates",
    )
    # The old spelling. Hidden rather than removed so a script written against
    # 0.3 keeps working; every other destructive command says --yes.
    e.add_argument("--force", dest="yes", action="store_true", help=argparse.SUPPRESS)
    e.add_argument(
        "--repeats",
        default="daily",
        help="recurrence across the date range (default: daily)",
    )
    _dry_run(e)
    _id_only(e)
    stdin_flags(e, "text")
    marks(e, "writes", "destructive")
    e.set_defaults(func=cmd_events_create, _destructive_when="--no-school")
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
    _dry_run(e)
    _yes(e)
    marks(e, "writes", "destructive")
    e.set_defaults(func=cmd_events_delete)

    p_st = sub.add_parser("students", help="list, create, update and delete students")
    s_st = p_st.add_subparsers(dest="students_command", required=True)
    st = s_st.add_parser("list", help="students in a class, or all of them")
    _class_id(st, help="omit for every student on the account")
    st.set_defaults(func=cmd_students_list)
    for verb, fn in (("create", cmd_students_create), ("update", cmd_students_update)):
        updating = verb == "update"
        st = s_st.add_parser(verb, help=f"{verb} a student")
        if updating:
            st.add_argument("--student-id", dest="student_id", required=True)
            _class_id(
                st,
                required=True,
                help="the class the student is in; read first so nothing is lost",
            )
        st.add_argument("--first-name", dest="first_name", required=not updating)
        st.add_argument("--last-name", dest="last_name", required=not updating)
        st.add_argument("--middle-name", dest="middle_name")
        st.add_argument("--code", help="student id/code used by the school")
        st.add_argument("--email")
        st.add_argument("--parent-email", dest="parent_email")
        st.add_argument("--phone")
        st.add_argument("--birthdate", metavar="MM/DD/YYYY", type=_date)
        _dry_run(st)
        if not updating:
            _id_only(st)
        marks(st, "writes")
        st.set_defaults(func=fn)
    st = s_st.add_parser("delete", help="delete a student")
    st.add_argument("--student-id", dest="student_id", required=True)
    st.add_argument(
        "--class-id",
        dest="class_id",
        help="the class the student is in. Without it there is no record to "
        "read back, so the delete cannot be verified",
    )
    _dry_run(st)
    marks(st, "writes", "destructive")
    st.set_defaults(func=cmd_students_delete)

    p = sub.add_parser("attendance", help="read attendance for a class on a date")
    _class_id(p, required=True)
    _date_arg(p, "--date", required=True)
    p.set_defaults(func=cmd_attendance)

    p = sub.add_parser("grades", help="grade periods and scored assignments")
    _class_id(p, required=True)
    p.set_defaults(func=cmd_grades)

    p = sub.add_parser("templates", help="lesson templates")
    p.add_argument("--teacher-id", dest="teacher_id")
    _raw(p)
    p.set_defaults(func=cmd_templates)

    for name, (path, _unwrap) in SIMPLE_READS.items():
        if name in ("events", "units", "todos", "students"):
            continue
        rp = sub.add_parser(name, help=f"read {name.replace('-', ' ')} ({path})")
        _raw(rp)
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
    # A same-named upload replaces the file in every lesson linked to it.
    _dry_run(a)
    marks(a, "writes")
    a.set_defaults(func=cmd_attachments_upload)

    p = sub.add_parser(
        "endpoints", help="list known API endpoints and how well they are mapped"
    )
    p.set_defaults(func=cmd_endpoints)

    p = sub.add_parser(
        "schema",
        help="dump every command, flag and error kind as JSON (contract "
        f"{CONTRACT_VERSION})",
        description="The machine-readable manifest of this CLI. One call "
        "replaces reading --help for every command group.",
    )
    p.set_defaults(func=cmd_schema)

    p = sub.add_parser(
        "check",
        help="preflight: verify the session, report hours left, and list class ids",
        description="Run this first. One round trip answers whether you are "
        "signed in, how long the token lasts, and which class ids exist.",
    )
    p.set_defaults(func=cmd_check)

    p = sub.add_parser(
        "raw", help="POST to any endpoint (escape hatch for unmapped calls)"
    )
    # The escape hatch reaches every endpoint, including the deleting ones.
    marks(p, "writes", "destructive")
    p.add_argument("path", help="endpoint path, e.g. /getAssignments")
    p.add_argument(
        "-F",
        "--field",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="form field; repeatable",
    )
    _verb = p.add_mutually_exclusive_group()
    _verb.add_argument(
        "--get",
        action="store_true",
        help="send as GET; some /services/planbook/** endpoints are GET-only "
        "and answer a POST with 405",
    )
    _verb.add_argument(
        "--json",
        action="store_true",
        help="send fields as a JSON body; a few service endpoints reject form "
        "encoding with \"A JSONObject text must begin with '{'\"",
    )
    _dry_run(p)
    p.set_defaults(func=cmd_raw)

    return parser


def _fail(exc: PlanbookError, *, as_json: bool) -> int:
    """Report a failure on stderr and return its exit code. stdout stays empty."""
    if as_json:
        json.dump(exc.to_dict(), sys.stderr)
        sys.stderr.write("\n")
    else:
        print(f"error: {exc}", file=sys.stderr)
        if exc.details:
            print(f"details: {json.dumps(exc.details, default=str)}", file=sys.stderr)
    return exc.exit_code


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    as_json = bool(getattr(args, "error_json", False))
    try:
        args.func(args)
    except PlanbookError as exc:
        return _fail(exc, as_json=as_json)
    except ValueError as exc:
        # int() on a non-numeric --class-id and friends: exit 64, not a traceback.
        return _fail(UsageError(f"invalid argument: {exc}"), as_json=as_json)
    except OSError as exc:
        return _fail(PlanbookError(str(exc)), as_json=as_json)
    except requests.RequestException as exc:
        return _fail(
            TransportError(f"could not reach Planbook: {exc}"), as_json=as_json
        )
    except EOFError:
        # A prompt with nothing on stdin - CI, a pipe: exit code, not a traceback.
        return _fail(
            UsageError(
                "no input available for a prompt.",
                remedy="Pass the value as an argument; this command needs a TTY.",
            ),
            as_json=as_json,
        )
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
