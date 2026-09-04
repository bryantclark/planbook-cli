"""The unit resource."""

import urllib.parse

import pytest
import responses

from conftest import (
    saved_lesson,
    stub,
    unit_list,
    unit_record,
)
from planbook.client import PlanbookClient
from planbook.errors import ApiError, UsageError
from planbook.resources.lessons import (
    set_lesson,
)
from planbook.resources.units import create_unit, delete_unit, unit_payload, update_unit


def test_unit_payload_sends_class_id_as_subject_id():
    payload = unit_payload(action="A", class_id=99, number="U1", title="T")
    assert payload["subjectId"] == "99"
    assert payload["action"] == "A"


@responses.activate
def test_set_lesson_carries_over_unit_sections_and_flags():
    # A fresh payload resets these to their defaults, so an edit that names
    # only the title used to silently drop the unit, the lock and section 4.
    stub(
        "/getLessonsEvents",
        saved_lesson(
            date="09/01/2026",
            lessonId=9,
            lessonTitle="Keep",
            lessonText="<p>b</p>",
            startTime="9:05 AM",
            endTime="9:55 AM",
            unitId=42,
            lessonLock="Y",
            extraLesson=0,
            linkedLessonId=0,
            tab4Text="<p>objectives</p>",
        ),
    )
    stub("/updateLesson", {"ok": True})
    # The read-back that proves the rename landed.
    stub(
        "/getLessonsEvents",
        saved_lesson(date="09/01/2026", lessonId=9, lessonTitle="Renamed"),
    )
    set_lesson(PlanbookClient("t.t.t"), class_id=1, date="09/01/2026", title="Renamed")
    sent = dict(
        urllib.parse.parse_qsl(
            [c for c in responses.calls if c.request.url.endswith("/updateLesson")][
                -1
            ].request.body
        )
    )
    assert sent["lessonTitle"] == "Renamed"
    assert sent["unitId"] == "42"
    assert sent["lessonLock"] == "Y"
    assert sent["tab4Text"] == "<p>objectives</p>"


@responses.activate
def test_update_unit_carries_over_what_the_caller_did_not_name():
    # /updateUnit replaces the whole record, so renaming a unit used to blank
    # its description, dates and section texts.
    stub(
        "/getUnits",
        unit_list(
            unit_record(
                unitNum="U1",
                unitTitle="Old",
                unitDesc="keep me",
                unitStart="09/01/2026",
                unitEnd="09/30/2026",
                unitLessonText="<p>plan</p>",
            )
        ),
    )
    stub("/updateUnit", {"ok": True})
    # The read-back that proves the new title landed.
    stub("/getUnits", unit_list(unit_record(unitTitle="New")))
    update_unit(PlanbookClient("t.t.t"), unit_id=5, class_id=1, title="New")
    sent = dict(
        urllib.parse.parse_qsl(
            [c for c in responses.calls if c.request.url.endswith("/updateUnit")][
                -1
            ].request.body
        )
    )
    assert sent["unitTitle"] == "New"
    assert sent["unitNum"] == "U1"
    assert sent["unitDesc"] == "keep me"
    assert sent["unitStart"] == "09/01/2026"
    assert sent["unitLessonText"] == "<p>plan</p>"


@responses.activate
def test_update_unit_refuses_a_class_the_unit_is_not_in():
    stub("/getUnits", unit_list(unit_record(unitTitle="Old")))
    with pytest.raises(UsageError):
        update_unit(PlanbookClient("t.t.t"), unit_id=5, class_id=2, title="New")
    assert not [c for c in responses.calls if c.request.url.endswith("/updateUnit")]


@responses.activate
def test_delete_unit_refuses_a_class_the_unit_is_not_in():
    stub("/getUnits", unit_list(unit_record(unitTitle="Old")))
    with pytest.raises(UsageError):
        delete_unit(PlanbookClient("t.t.t"), unit_id=5, class_id=2)
    assert not [c for c in responses.calls if c.request.url.endswith("/updateUnit")]


@responses.activate
def test_delete_unit_sends_the_delete_action():
    stub("/getUnits", unit_list(unit_record(unitTitle="Old")))
    stub("/updateUnit", {"ok": True})
    # The read-back that proves the delete took: the unit is gone afterwards.
    stub("/getUnits", unit_list())
    delete_unit(PlanbookClient("t.t.t"), unit_id=5, class_id=1)
    sent = dict(
        urllib.parse.parse_qsl(
            [c for c in responses.calls if c.request.url.endswith("/updateUnit")][
                -1
            ].request.body
        )
    )
    assert sent["action"] == "D"
    assert sent["unitId"] == "5"


@responses.activate
def test_create_unit_raises_when_nothing_was_created():
    stub("/getUnits", unit_list())
    stub("/updateUnit", {"ok": True})
    with pytest.raises(ApiError):
        create_unit(PlanbookClient("t.t.t"), class_id=1, number="U1", title="Intro")


@responses.activate
def test_update_unit_raises_on_a_missing_id_instead_of_blanking():
    # Same guard as update_todo: an unknown id must not write blank fields.
    stub("/getUnits", unit_list())
    with pytest.raises(ApiError):
        update_unit(PlanbookClient("t.t.t"), unit_id=999, class_id=1, title="X")
