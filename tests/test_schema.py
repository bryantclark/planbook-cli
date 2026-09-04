"""The schema manifest, the preflight check and structured errors.

These are the parts an agent parses, so a change here is a contract
change.
"""

import json

import pytest
import responses

from conftest import (
    class_wire_record,
    parse_stdout,
    stub,
)
from planbook import cli, schema
from planbook.contract import CONTRACT_VERSION
from planbook.errors import (
    SchemaDrift,
)

# --- structured errors -----------------------------------------------------


def test_error_json_puts_one_object_on_stderr_and_nothing_on_stdout(
    capsys, isolated_config
):
    code = cli.main(["--error-json", "classes", "list"])
    captured = capsys.readouterr()
    assert code == 77
    assert captured.out == ""
    error = json.loads(captured.err)["error"]
    assert error["kind"] == "NotAuthenticated"
    assert error["code"] == 77
    assert error["retryable"] is False
    assert error["contract"] == CONTRACT_VERSION
    assert "auth import" in error["remedy"]


def test_error_json_can_be_switched_on_by_environment(
    capsys, isolated_config, monkeypatch
):
    monkeypatch.setenv("PLANBOOK_ERROR_JSON", "1")
    cli.main(["classes", "list"])
    assert json.loads(capsys.readouterr().err)["error"]["kind"] == "NotAuthenticated"


def test_prose_stays_the_default(capsys, isolated_config):
    cli.main(["classes", "list"])
    captured = capsys.readouterr()
    assert captured.err.startswith("error: ")
    with pytest.raises(ValueError):
        json.loads(captured.err)


def test_every_error_kind_reports_a_code_and_a_remedy():
    for entry in schema.manifest(cli.build_parser())["errors"]:
        assert entry["code"] in (1, 64, 65, 77)
        assert entry["remedy"]
        assert isinstance(entry["retryable"], bool)


def test_schema_drift_is_not_retryable_and_says_stop():
    assert SchemaDrift.retryable is False
    assert "do not retry" in SchemaDrift.remedy.lower()


# --- the schema manifest ---------------------------------------------------


def test_schema_describes_every_command_with_its_flags(capsys, isolated_config):
    assert cli.main(["schema"]) == 0
    body, _ = parse_stdout(capsys)
    assert body["contract"] == CONTRACT_VERSION
    names = {c["command"] for c in body["commands"]}
    assert {"lessons set", "classes create", "units delete", "check"} <= names
    lesson_set = next(c for c in body["commands"] if c["command"] == "lessons set")
    assert lesson_set["writes"] and lesson_set["dry_run"]
    flags = {a["name"]: a for a in lesson_set["arguments"]}
    assert flags["--class-id"]["required"] is True
    assert flags["--date"]["type"] == "date"
    assert flags["--section"]["repeatable"] is True
    assert flags["--text"]["accepts_stdin"] is True


def test_schema_marks_deletes_destructive_and_creates_id_returning(
    capsys, isolated_config
):
    cli.main(["schema"])
    body, _ = parse_stdout(capsys)
    by_name = {c["command"]: c for c in body["commands"]}
    assert by_name["classes delete"]["destructive"] is True
    assert by_name["classes list"]["destructive"] is False
    assert by_name["units create"]["returns_id"] is True


def test_schema_shows_one_spelling_for_confirmation(capsys, isolated_config):
    # An agent learns --yes once. A hidden alias must not leak into the manifest.
    cli.main(["schema"])
    body, _ = parse_stdout(capsys)
    for command in body["commands"]:
        names = {a["name"] for a in command["arguments"]}
        assert "--force" not in names, command["command"]
    by_name = {c["command"]: c for c in body["commands"]}
    assert "--yes" in {a["name"] for a in by_name["events create"]["arguments"]}


def test_schema_publishes_the_id_convention(capsys, isolated_config):
    cli.main(["schema"])
    body, _ = parse_stdout(capsys)
    assert body["conventions"]["id_key"] == "id"


@responses.activate
def test_check_answers_auth_token_life_and_class_ids_in_one_round_trip(
    capsys, session_file
):
    stub(
        "/getClasses2",
        {
            "currentYearId": 7,
            "classes": [class_wire_record(teach_days=("m", "w"))],
        },
    )
    assert cli.main(["check"]) == 0
    body, _ = parse_stdout(capsys)
    assert body["authenticated"] is True
    assert body["current_year_id"] == 7
    assert body["classes"][0]["id"] == 123
    assert body["classes"][0]["days"] == ["monday", "wednesday"]
    assert "expires_in_hours" in body
    assert len(responses.calls) == 1


def test_schema_advertises_stdin_only_where_a_command_reads_it(capsys, isolated_config):
    # Sniffing the help prose for this published a write flag on commands that
    # stored the literal dash.
    cli.main(["schema"])
    body, _ = parse_stdout(capsys)
    advertised = {
        (c["command"], a["name"])
        for c in body["commands"]
        for a in c["arguments"]
        if a.get("accepts_stdin")
    }
    assert ("todos update", "--text") in advertised
    assert ("events create", "--text") in advertised
    assert ("lessons set", "--section") in advertised


def test_a_command_keeps_every_mark_it_declares(capsys, isolated_config):
    # marks() assigned rather than accumulated, so a second call erased the
    # first and the manifest called a destructive command safe.
    cli.main(["schema"])
    body, _ = parse_stdout(capsys)
    delete = next(c for c in body["commands"] if c["command"] == "lessons delete")
    assert delete["writes"] and delete["destructive"] and delete["dry_run"]
    upload = next(c for c in body["commands"] if c["command"] == "attachments upload")
    assert upload["writes"] and upload["dry_run"] and not upload["destructive"]
