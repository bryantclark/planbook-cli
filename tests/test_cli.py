import json

import pytest
import responses

from planbook import cli
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
        json={"currentYearId": 1, "classes": [], "lessonBanks": [], "districtLessonBanks": []},
    )
    code = cli.main(["classes", "list"])
    body, captured = parse_stdout(capsys)
    assert code == 0
    assert captured.out == json.dumps(body, indent=2) + "\n"
    assert body["current_year_id"] == 1


def test_usage_error_exit_code_64_for_bad_days(capsys, isolated_config):
    code = cli.main(["classes", "create", "--name", "X", "--start", "08/31/2026", "--end", "06/06/2027", "--days", "X"])
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
    code = cli.main([
        "lessons", "set",
        "--class-id", "123",
        "--date", "09/03/2026",
        "--title", "Photosynthesis",
        "--dry-run",
    ])
    body, _ = parse_stdout(capsys)
    assert code == 0
    assert body["dry_run"] is True
    assert len(responses.calls) == 0


@responses.activate
def test_raw_dry_run_does_not_touch_auth(capsys, isolated_config):
    code = cli.main(["raw", "/getAssignments", "-F", "teacherId=123", "--dry-run"])
    body, _ = parse_stdout(capsys)
    assert code == 0
    assert body == {"dry_run": True, "endpoint": "/getAssignments", "payload": {"teacherId": "123"}}
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


@responses.activate
def test_bulk_keep_going_records_failure_and_exits_nonzero(tmp_path, capsys, session_file):
    path = tmp_path / "lessons.json"
    path.write_text(json.dumps([
        {"class_id": 123, "date": "09/03/2026", "title": "Ok"},
        {"class_id": 123, "date": "09/04/2026"},
        {"class_id": 123, "date": "09/05/2026", "text": "Still runs"},
    ]))
    responses.post(f"{API_BASE}/updateLesson", json={"ok": True})
    responses.post(f"{API_BASE}/updateLesson", json={"ok": True})

    with pytest.raises(SystemExit) as exc:
        cli.main(["lessons", "bulk", str(path), "--keep-going"])
    body, _ = parse_stdout(capsys)

    assert exc.value.code == 1
    assert body["written"] == 2
    assert body["failed"] == 1
    assert body["results"][1]["ok"] is False
    assert len(responses.calls) == 2


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
