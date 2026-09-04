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
