import json
import urllib.parse

import pytest
import responses

from conftest import DATE, event_list, lesson_days, saved_lesson, stub
from planbook import cli
from planbook.client import API_BASE, PlanbookClient
from planbook.resources.events import new_event_payload
from planbook.resources.lessons import set_lesson


def parse_stdout(capsys):
    captured = capsys.readouterr()
    return json.loads(captured.out), captured


def write_session(session_file):
    return session_file


@responses.activate
def test_success_path_prints_only_valid_json_stdout(capsys, session_file):
    stub(
        "/getClasses2",
        {
            "currentYearId": 1,
            "classes": [],
            "lessonBanks": [],
            "districtLessonBanks": [],
        },
    )
    code = cli.main(["classes", "list"])
    body, captured = parse_stdout(capsys)
    assert code == 0
    assert captured.out == json.dumps(body, indent=2) + "\n"
    assert body["current_year_id"] == 1


def test_usage_error_exit_code_64_for_bad_days(capsys, isolated_config):
    code = cli.main(
        [
            "classes",
            "create",
            "--name",
            "X",
            "--start",
            "08/31/2026",
            "--end",
            "06/06/2027",
            "--days",
            "X",
        ]
    )
    captured = capsys.readouterr()
    assert code == 64
    assert captured.out == ""


@responses.activate
def test_schema_drift_exit_code_65(capsys, session_file):
    stub("/getClasses2", {"currentYearId": 1})
    code = cli.main(["classes", "list"])
    captured = capsys.readouterr()
    assert code == 65
    assert captured.out == ""


def test_not_authenticated_exit_code_77(capsys, isolated_config):
    code = cli.main(["classes", "list"])
    captured = capsys.readouterr()
    assert code == 77
    assert captured.out == ""


@responses.activate
def test_lessons_set_dry_run_previews_what_the_write_would_carry_over(
    capsys, session_file
):
    # The preview reads the current lesson for the same reason the write does:
    # a payload built without it shows this write blanking text the real one
    # keeps, which is the one thing --dry-run exists to catch.
    stub(
        "/getLessonsEvents",
        saved_lesson(
            classId=123,
            lessonId=7,
            lessonTitle="Old title",
            lessonText="<p>keep me</p>",
        ),
    )
    code = cli.main(
        [
            "lessons",
            "set",
            "--class-id",
            "123",
            "--date",
            "09/03/2026",
            "--title",
            "Photosynthesis",
            "--dry-run",
        ]
    )
    body, _ = parse_stdout(capsys)
    assert code == 0
    assert body["dry_run"] is True
    assert body["payload"]["lessonTitle"] == "Photosynthesis"
    assert body["payload"]["lessonText"] == "<p>keep me</p>"
    assert not [c for c in responses.calls if c.request.url.endswith("/updateLesson")]


@responses.activate
def test_raw_dry_run_does_not_touch_auth(capsys, isolated_config):
    code = cli.main(["raw", "/getAssignments", "-F", "teacherId=123", "--dry-run"])
    body, _ = parse_stdout(capsys)
    assert code == 0
    assert body["dry_run"] is True
    assert body["requests"] == [
        {
            "method": "POST",
            "endpoint": "/getAssignments",
            "payload": {"teacherId": "123"},
        }
    ]
    assert body["endpoint"] == "/getAssignments"
    assert body["payload"] == {"teacherId": "123"}
    assert len(responses.calls) == 0


def test_endpoints_shape(capsys, isolated_config):
    code = cli.main(["endpoints"])
    body, _ = parse_stdout(capsys)
    assert code == 0
    assert isinstance(body, list)
    assert body
    assert all({"path", "status", "description"} <= set(item) for item in body)


def test_bulk_malformed_file_exits_64(tmp_path, capsys, isolated_config):
    path = tmp_path / "bad.json"
    path.write_text("{")
    code = cli.main(["lessons", "bulk", str(path), "--dry-run"])
    captured = capsys.readouterr()
    assert code == 64
    assert captured.out == ""


def test_bulk_rejects_a_bad_item_before_writing_anything(
    tmp_path, capsys, session_file
):
    # SKILL.md promises a typo cannot half-apply a week, so value errors must
    # surface in the pre-flight pass, not mid-write.
    path = tmp_path / "lessons.json"
    path.write_text(
        json.dumps(
            [
                {"class_id": 123, "date": "09/03/2026", "title": "Ok"},
                {"class_id": 123, "date": "09/04/2026", "start_time": "9:00"},
            ]
        )
    )
    assert cli.main(["lessons", "bulk", str(path)]) == 64
    assert len(responses.calls) == 0


@responses.activate
def test_bulk_reads_the_section_layout_once(tmp_path, capsys, session_file):
    stub("/getSettings", {"tab4Label": "Objectives", "tab4Enabled": "Y"})
    # The dry run now reads each lesson so its preview shows the carry-over.
    stub("/getLessonsEvents", lesson_days())
    path = tmp_path / "lessons.json"
    path.write_text(
        json.dumps(
            [
                {"class_id": 1, "date": "09/03/2026", "sections": {"Objectives": "a"}},
                {"class_id": 1, "date": "09/04/2026", "sections": {"Objectives": "b"}},
                {"class_id": 1, "date": "09/05/2026", "sections": {"Objectives": "c"}},
            ]
        )
    )
    assert cli.main(["lessons", "bulk", str(path), "--dry-run"]) == 0
    settings_calls = [
        c for c in responses.calls if c.request.url.endswith("/getSettings")
    ]
    assert len(settings_calls) == 1


@responses.activate
def test_bulk_keep_going_continues_past_an_api_failure(tmp_path, capsys, session_file):
    # An API-level failure can only be found at write time; --keep-going
    # records it, carries on, and still exits non-zero.
    path = tmp_path / "lessons.json"
    path.write_text(
        json.dumps(
            [
                {"class_id": 123, "date": "09/03/2026", "title": "One"},
                {"class_id": 123, "date": "09/04/2026", "title": "Two"},
            ]
        )
    )
    stub("/getEvents", event_list())
    stub("/getLessonsEvents", lesson_days())
    stub("/getLessonsEvents", lesson_days())
    # The read-back after the second item's write, which proves it landed.
    stub(
        "/getLessonsEvents",
        saved_lesson(date="09/04/2026", classId=123, lessonId=8, lessonTitle="Two"),
    )
    stub("/updateLesson", {"error": "true", "msg": "nope"})
    stub("/updateLesson", {"ok": True})

    with pytest.raises(SystemExit) as exc:
        cli.main(["lessons", "bulk", str(path), "--keep-going"])
    assert exc.value.code == 1
    body = json.loads(capsys.readouterr().out)
    assert body["failed"] == 1
    assert body["written"] == 1


def test_argparse_errors_exit_64(capsys, isolated_config):
    # AGENTS.md promises 64 for a bad command line; argparse's own default is 2.
    for argv in (["no-such-command"], ["lessons", "set"], ["classes"]):
        try:
            cli.main(argv)
        except SystemExit as exc:
            assert exc.code == 64, argv
        else:  # pragma: no cover
            raise AssertionError(f"{argv} did not exit")


def test_malformed_token_file_is_not_a_traceback(capsys, isolated_config):
    path = isolated_config / "planbook"
    path.mkdir(parents=True, exist_ok=True)
    (path / "token.json").write_text('{"token": 12345}')
    assert cli.main(["classes", "list"]) == 77


@responses.activate
def test_events_delete_dry_run_sends_no_delete(capsys, session_file):
    # The flag existed, was advertised, and performed the delete anyway.
    stub(
        "/getEvents",
        event_list({"eventId": 7, "eventTitle": "Holiday", "eventDate": "09/07/2026"}),
    )
    assert cli.main(["events", "delete", "--event-id", "7", "--dry-run"]) == 0
    assert not [c for c in responses.calls if c.request.url.endswith("/deleteEvent")]
    assert json.loads(capsys.readouterr().out)["dry_run"] is True


@responses.activate
def test_raw_json_actually_sends_json(capsys, session_file):
    stub("/x", {})
    assert cli.main(["raw", "/x", "-F", "a=1", "--json", "--yes"]) == 0
    assert responses.calls[0].request.headers["Content-Type"] == "application/json"


@responses.activate
def test_raw_write_needs_yes_and_sends_nothing_without_it(capsys, session_file):
    stub("/deleteClass", {})
    assert cli.main(["raw", "/deleteClass", "-F", "classId=1"]) == 64
    assert len(responses.calls) == 0
    assert capsys.readouterr().out == ""


@responses.activate
def test_raw_get_needs_no_confirmation(capsys, session_file):
    responses.get(f"{API_BASE}/services/planbook/x", json={"ok": True})
    assert cli.main(["raw", "/services/planbook/x", "--get"]) == 0


def test_raw_write_previews_as_destructive(capsys, isolated_config):
    assert cli.main(["raw", "/deleteClass", "-F", "classId=1", "--dry-run"]) == 0
    assert parse_stdout(capsys)[0]["destructive"] is True


def test_raw_get_previews_as_read_only(capsys, isolated_config):
    assert cli.main(["raw", "/getAssignments", "--get", "--dry-run"]) == 0
    assert parse_stdout(capsys)[0]["destructive"] is False


def test_events_create_dry_run_previews_the_payload_the_write_would_send(capsys):
    # The preview used to build its own payload and had drifted from the real
    # one, omitting updatedFields and updateCurrentEvent.
    assert (
        cli.main(
            ["events", "create", "--title", "T", "--date", "09/01/2026", "--dry-run"]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)["payload"]
    assert payload == new_event_payload(title="T", date="09/01/2026")


def test_auth_token_without_stdin_exits_64_not_traceback(monkeypatch):
    # A prompt with no input (CI, a pipe) must honour the exit-code contract.
    def no_input(*_a, **_k):
        raise EOFError

    monkeypatch.setattr("getpass.getpass", no_input)
    assert cli.main(["auth", "token"]) == 64


def test_unknown_auth_subcommands_are_rejected(capsys):
    for command in ("login", "browser", "signin"):
        with pytest.raises(SystemExit) as exc:
            cli.main(["auth", command])
        assert exc.value.code == 64


def test_raw_get_and_json_are_mutually_exclusive():
    # argparse rejects the pair before dispatch, exiting 64 via _Parser.error.
    with pytest.raises(SystemExit) as exc:
        cli.main(["raw", "/x", "--get", "--json"])
    assert exc.value.code == 64


def test_todos_create_dry_run_is_offline(capsys):
    # A create preview must not need a session.
    assert (
        cli.main(
            ["todos", "create", "--text", "Grade", "--start", "09/01/2026", "--dry-run"]
        )
        == 0
    )
    out = json.loads(capsys.readouterr().out)
    assert out["dry_run"] is True
    assert out["endpoint"] == "/updateToDo"


def test_students_create_dry_run_is_offline(capsys):
    assert (
        cli.main(
            [
                "students",
                "create",
                "--first-name",
                "Ada",
                "--last-name",
                "L",
                "--dry-run",
            ]
        )
        == 0
    )
    out = json.loads(capsys.readouterr().out)
    assert out["dry_run"] is True
    assert out["payload"]["studentFirstName"] == "Ada"


@responses.activate
def test_lessons_get_projects_and_raw_returns_the_wire_record(capsys, session_file):
    wire = saved_lesson(lessonText="<p>a &amp; b</p>", homeworkText="read ch. 4")
    stub("/getLessonsEvents", wire)
    stub("/getLessonsEvents", wire)
    args = ["lessons", "get", "--class-id", "1", "--date", DATE]
    assert cli.main(args) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["text"] == "<p>a &amp; b</p>"
    assert out["homework"] == "read ch. 4"
    assert out["date"] == DATE
    assert "lessonText" not in out
    assert cli.main([*args, "--raw"]) == 0
    assert "lessonText" in json.loads(capsys.readouterr().out)


@responses.activate
def test_check_does_not_call_a_broken_endpoint_a_sign_in_problem(
    capsys, monkeypatch, tmp_path
):
    # `check` is the first call every agent makes. Reporting exit 77 here sends
    # a signed-in user to re-authenticate over a server-side fault.
    session = tmp_path / "token.json"
    session.write_text(json.dumps({"token": "t.t.t"}))
    monkeypatch.setattr("planbook.config.session_path", lambda: session)
    monkeypatch.delenv("PLANBOOK_TOKEN", raising=False)
    stub("/getClasses2", {"error": "true", "msg": "date must not be null"})
    assert cli.main(["check"]) == 1
    captured = capsys.readouterr()
    assert captured.out.strip() == ""
    assert "date must not be null" in captured.err


@responses.activate
def test_auth_status_reports_a_live_session_when_classes_break(
    capsys, monkeypatch, tmp_path
):
    # A broken `/getClasses2` is not a rejected session; saying so sends a
    # signed-in user to sign in again.
    # "t.t.t" has no exp claim, so the client treats it as unexpired.
    session = tmp_path / "token.json"
    session.write_text(json.dumps({"token": "t.t.t"}))
    monkeypatch.setattr("planbook.config.session_path", lambda: session)
    monkeypatch.delenv("PLANBOOK_TOKEN", raising=False)
    stub("/getClasses2", {"error": "true", "msg": "nope"})
    assert cli.main(["auth", "status"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["authenticated"] is True
    assert "nope" in out["classes_unavailable"]


@responses.activate
def test_auth_status_keeps_stdout_empty_when_the_token_is_rejected(
    capsys, monkeypatch, tmp_path
):
    # The output contract: stdout is JSON on success, empty on failure.
    session = tmp_path / "token.json"
    session.write_text(json.dumps({"token": "t.t.t"}))
    monkeypatch.setattr("planbook.config.session_path", lambda: session)
    monkeypatch.delenv("PLANBOOK_TOKEN", raising=False)
    stub("/getClasses2", {"notLoggedIn": "true"})
    assert cli.main(["auth", "status"]) == 77
    captured = capsys.readouterr()
    assert captured.out.strip() == ""


def test_bulk_rejects_a_non_string_text_field(tmp_path):
    # A bulk item with a numeric title must be a usage error, not a payload
    # with a non-string value silently sent to the server.
    f = tmp_path / "b.json"
    f.write_text(json.dumps([{"date": "09/03/2026", "title": 123}]))
    assert cli.main(["lessons", "bulk", str(f), "--class-id", "1", "--dry-run"]) == 64


def test_auth_import_does_not_open_a_browser_when_non_interactive(monkeypatch):
    # Agents/CI (no TTY) must get the typed error, never a browser or a wait.
    from planbook.commands import auth as authcmd

    monkeypatch.setattr(authcmd, "_best_browser_token", lambda args: None)
    monkeypatch.setattr(authcmd.config, "load_session_or_none", lambda: None)
    monkeypatch.setattr(authcmd.browser_cookies, "diagnose", lambda: {})
    opened = []
    monkeypatch.setattr(authcmd.webbrowser, "open", lambda url: opened.append(url))
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)

    assert cli.main(["auth", "import"]) == 64
    assert opened == []


def test_auth_import_guides_to_a_readable_browser_when_none_readable(monkeypatch):
    # Safari-only machine: don't poll a store we can't read; give the redirect.
    from planbook.commands import auth as authcmd

    monkeypatch.setattr(authcmd, "_best_browser_token", lambda args: None)
    monkeypatch.setattr(authcmd.config, "load_session_or_none", lambda: None)
    monkeypatch.setattr(authcmd.browser_cookies, "any_store_readable", lambda: False)
    opened = []
    monkeypatch.setattr(authcmd.webbrowser, "open", lambda url: opened.append(url))
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("sys.stderr.isatty", lambda: True)

    assert cli.main(["auth", "import"]) == 64
    assert opened == []


@responses.activate
def test_bulk_writes_an_item_that_only_moves_a_lesson_into_a_unit(
    tmp_path, capsys, session_file
):
    # `unit_id` is a bulk key, and the payload guard counts it, so a unit-only
    # item is a write like any other rather than a usage error.
    path = tmp_path / "lessons.json"
    path.write_text(json.dumps([{"class_id": 123, "date": "09/03/2026", "unit_id": 9}]))
    cells = {"classId": 123, "lessonTitle": "Cells", "lessonText": "<p>Mitosis</p>"}
    stub("/getEvents", event_list())
    stub("/getLessonsEvents", saved_lesson(**cells))
    stub("/updateLesson", {"ok": True})
    stub("/getLessonsEvents", saved_lesson(**cells, unitId=9))

    assert cli.main(["lessons", "bulk", str(path)]) == 0
    body = json.loads(capsys.readouterr().out)
    assert body["written"] == 1
    sent = urllib.parse.parse_qs(responses.calls[2].request.body)
    assert sent["unitId"] == ["9"]
    assert sent["lessonText"] == ["<p>Mitosis</p>"]


@responses.activate
def test_a_unit_and_a_standard_create_the_lesson_the_standard_needs(session_file):
    # Standards go to `checks`, not `named`, so a unit-only refusal keyed on
    # `named` alone would block the create-then-attach path.
    created = saved_lesson(unitId=9, standards=[{"id": "3.NBT.A.1"}])
    stub("/getLessonsEvents", lesson_days())
    stub("/updateLesson", {"ok": True})
    stub("/getLessonsEvents", created)
    stub("/updateLesson", {"ok": True})
    stub("/getLessonsEvents", created)

    result = set_lesson(
        PlanbookClient("t.t.t"),
        class_id=1,
        date="09/03/2026",
        unit_id=9,
        standards=["1234"],
    )
    assert result["ok"] is True
    # Nested, so a real run and its `--dry-run` preview read the same.
    assert result["effects"]["standards"] == ["1234"]
