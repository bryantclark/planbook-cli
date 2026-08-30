import json

import pytest
import responses

from planbook import api, cli
from planbook.client import API_BASE


def parse_stdout(capsys):
    captured = capsys.readouterr()
    return json.loads(captured.out), captured


def write_session(session_file):
    return session_file


@responses.activate
def test_success_path_prints_only_valid_json_stdout(capsys, session_file):
    responses.post(
        f"{API_BASE}/getClasses2",
        json={
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
    responses.post(f"{API_BASE}/getClasses2", json={"currentYearId": 1})
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
def test_lessons_set_dry_run_does_not_touch_auth(capsys, isolated_config):
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
    assert len(responses.calls) == 0


@responses.activate
def test_raw_dry_run_does_not_touch_auth(capsys, isolated_config):
    code = cli.main(["raw", "/getAssignments", "-F", "teacherId=123", "--dry-run"])
    body, _ = parse_stdout(capsys)
    assert code == 0
    assert body == {
        "dry_run": True,
        "method": "POST",
        "endpoint": "/getAssignments",
        "payload": {"teacherId": "123"},
    }
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
    responses.post(f"{API_BASE}/getEvents", json={"events": []})
    responses.post(f"{API_BASE}/getLessonsEvents", json={"days": []})
    responses.post(f"{API_BASE}/updateLesson", json={"error": "true", "msg": "nope"})
    responses.post(f"{API_BASE}/updateLesson", json={"ok": True})

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
    responses.post(
        f"{API_BASE}/getEvents",
        json={
            "events": [
                {"eventId": 7, "eventTitle": "Holiday", "eventDate": "09/07/2026"}
            ]
        },
    )
    assert cli.main(["events", "delete", "--event-id", "7", "--dry-run"]) == 0
    assert not [c for c in responses.calls if c.request.url.endswith("/deleteEvent")]
    assert json.loads(capsys.readouterr().out)["dry_run"] is True


@responses.activate
def test_raw_json_actually_sends_json(capsys, session_file):
    responses.post(f"{API_BASE}/x", json={})
    assert cli.main(["raw", "/x", "-F", "a=1", "--json"]) == 0
    assert responses.calls[0].request.headers["Content-Type"] == "application/json"


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
    assert payload == api.new_event_payload(title="T", date="09/01/2026")
