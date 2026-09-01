"""Opt-in contract tests against the real Planbook API.

Every other test mocks HTTP, so nothing else catches the API changing shape
under a projection that still parses its own fixtures. These read the live
account and check that each mapped reader still returns what it promises.

They are skipped unless `PLANBOOK_LIVE=1`, so a plain `pytest` stays offline:

    PLANBOOK_LIVE=1 pytest tests/live/test_contract.py -q

They only read. No test here writes, and none may be given one.
"""

from __future__ import annotations

import datetime
import os

import pytest

from planbook import config
from planbook.client import PlanbookClient
from planbook.resources.classes import get_class, list_classes
from planbook.resources.events import list_events
from planbook.resources.lessons import lesson_sections, read_week
from planbook.resources.misc import settings, standards
from planbook.resources.people import list_students, list_templates
from planbook.resources.todos import list_todos
from planbook.resources.units import list_units

LIVE = os.environ.get("PLANBOOK_LIVE") == "1"

# Read at import, which is before conftest's isolated_config rewrites HOME.
TOKEN = config.load_session_or_none() if LIVE else None

pytestmark = pytest.mark.skipif(
    not LIVE, reason="set PLANBOOK_LIVE=1 to run against the real API"
)


@pytest.fixture(scope="session")
def client() -> PlanbookClient:
    if not TOKEN:
        pytest.fail("No stored session. Run `planbook auth import` first.")
    return PlanbookClient(TOKEN)


@pytest.fixture(scope="session")
def account(client: PlanbookClient) -> dict[str, object]:
    body = list_classes(client)
    if not body["classes"]:
        pytest.skip("The account has no classes, so there is nothing to check.")
    first = body["classes"][0]
    return {
        "year_id": body["current_year_id"],
        "class_id": first["id"],
        "teacher_id": first.get("teacher_id"),
    }


def has_keys(record: object, *keys: str) -> None:
    assert isinstance(record, dict)
    missing = [k for k in keys if k not in record]
    assert not missing, f"missing {missing} from {sorted(record)}"


def test_classes_list_still_projects_the_documented_keys(client):
    body = list_classes(client)
    has_keys(body, "current_year_id", "classes")
    for record in body["classes"]:
        has_keys(record, "id", "name", "start_date", "end_date", "schedule")


def test_classes_get_still_returns_a_named_class(client, account):
    record = get_class(client, account["class_id"])
    has_keys(record, "className")


def test_lessons_week_still_decodes(client):
    today = datetime.date.today()
    monday = today - datetime.timedelta(days=today.weekday())
    for day in read_week(client, monday=monday.strftime("%m/%d/%Y")):
        has_keys(day, "date", "day_of_week", "lessons")
        for lesson in day["lessons"]:
            has_keys(lesson, "class_id", "lesson_id", "title", "text")


def test_lesson_sections_are_still_six(client):
    sections = lesson_sections(client)
    assert [s["section"] for s in sections] == [1, 2, 3, 4, 5, 6]
    for section in sections:
        has_keys(section, "section", "label", "enabled", "field")


def test_units_todos_and_events_still_project(client):
    for record in list_units(client):
        has_keys(record, "id", "class_id", "title", "sections")
    for record in list_todos(client):
        has_keys(record, "id", "text", "done")
    for record in list_events(client):
        has_keys(record, "id", "title", "date", "no_school")


def test_students_still_carry_an_id(client, account):
    for record in list_students(client):
        has_keys(record, "id")
    for record in list_students(client, class_id=account["class_id"]):
        has_keys(record, "id", "name")


def test_templates_and_settings_still_read(client, account):
    if account["teacher_id"]:
        for record in list_templates(client, teacher_id=account["teacher_id"]):
            has_keys(record, "id", "name")
    assert isinstance(settings(client), dict)


def test_standards_search_still_returns_records(client):
    for record in standards(client, search="")[:5]:
        assert isinstance(record, dict)
