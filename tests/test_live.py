"""The one test that talks to api.planbook.com, and only when asked.

Every other test mocks HTTP, so schema drift upstream can only ever show up in
production. This is the early warning: a read-only preflight against a real
account, run by hand before a release. Skipped unless `PLANBOOK_LIVE_TOKEN` is
set - the autouse config isolation strips `PLANBOOK_TOKEN` itself, so the
token is captured here at import, before any fixture runs.

    PLANBOOK_LIVE_TOKEN=$(jq -r .token ~/.config/planbook/token.json) pytest tests/test_live.py
"""

import os

import pytest

from conftest import parse_stdout
from planbook import cli
from planbook.contract import CONTRACT_VERSION

LIVE_TOKEN = os.environ.get("PLANBOOK_LIVE_TOKEN")

pytestmark = pytest.mark.skipif(
    not LIVE_TOKEN, reason="set PLANBOOK_LIVE_TOKEN to run against the real API"
)


def test_check_against_the_real_api(capsys, monkeypatch):
    monkeypatch.setenv("PLANBOOK_TOKEN", LIVE_TOKEN or "")
    assert cli.main(["check"]) == 0
    body, _ = parse_stdout(capsys)
    assert body["contract"] == CONTRACT_VERSION
    assert body["authenticated"] is True
    assert isinstance(body["current_year_id"], int)
    for klass in body["classes"]:
        assert isinstance(klass["id"], int)
        assert klass["name"]
        assert set(klass["days"]) <= set("MTWRFSU")


@pytest.fixture(scope="module")
def live_session():
    """One `check` for the whole sweep: the real class id and the account id."""
    os.environ["PLANBOOK_TOKEN"] = LIVE_TOKEN or ""
    import io
    from contextlib import redirect_stdout

    out = io.StringIO()
    with redirect_stdout(out):
        assert cli.main(["check"]) == 0
    import json

    body = json.loads(out.getvalue())
    assert body["classes"], "the live sweep needs at least one class"
    return body


def _run(monkeypatch, capsys, argv: list[str]) -> object:
    monkeypatch.setenv("PLANBOOK_TOKEN", LIVE_TOKEN or "")
    assert cli.main(argv) == 0, f"{' '.join(argv)} did not exit 0"
    body, _ = parse_stdout(capsys)
    return body


READS_WITHOUT_ARGS = [
    ["classes", "list"],
    ["units", "list"],
    ["todos", "list"],
    ["events", "list"],
    ["students", "list"],
    ["templates"],
    ["assignments"],
    ["assessments"],
    ["schools"],
    ["comments"],
    ["settings"],
    ["standards"],
    ["lessons", "sections"],
    ["schedule", "special-days"],
    ["attachments", "list"],
]


@pytest.mark.parametrize("argv", READS_WITHOUT_ARGS, ids=" ".join)
def test_every_account_read_still_parses(argv, capsys, monkeypatch, live_session):
    """Each read projects without SchemaDrift. Exit 65 here means the API moved."""
    _run(monkeypatch, capsys, argv)


def test_every_class_read_still_parses(capsys, monkeypatch, live_session):
    klass = live_session["classes"][0]
    class_id = str(klass["id"])
    date = klass["start_date"]
    for argv in (
        ["classes", "get", "--class-id", class_id],
        ["lessons", "week", "--monday", date],
        ["lessons", "get", "--class-id", class_id, "--date", date],
        ["grades", "--class-id", class_id],
        ["attendance", "--class-id", class_id, "--date", date],
        ["students", "list", "--class-id", class_id],
        ["todos", "list", "--class-id", class_id],
    ):
        _run(monkeypatch, capsys, argv)


def test_every_list_answers_to_id(capsys, monkeypatch, live_session):
    """The contract every agent leans on: each record in each list has an int id."""
    for argv in (
        ["classes", "list"],
        ["units", "list"],
        ["todos", "list"],
        ["events", "list"],
        ["students", "list"],
        ["templates"],
    ):
        body = _run(monkeypatch, capsys, argv)
        assert isinstance(body, list), f"{argv}: lists are top-level JSON arrays"
        for record in body:
            assert isinstance(record.get("id"), int), f"{argv}: {record}"
