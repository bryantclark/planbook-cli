"""The event resource, including the no-school guard."""

import urllib.parse

import pytest
import responses

from conftest import (
    event_list,
    event_record,
    lesson_days,
    saved_lesson,
    stub,
)
from planbook.client import PlanbookClient
from planbook.errors import UsageError
from planbook.resources.events import create_event, event_payload


def test_event_payload_commits_rather_than_only_validating():
    # verifyShift="true" answers exactly like success and writes nothing.
    payload = event_payload(
        {"eventTitle": "X", "eventDate": "09/15/2026", "endDate": "09/15/2026"}
    )
    assert payload["verifyShift"] == "false"
    assert payload["eventCurrentDate"] == ""
    assert payload["shiftLessons"] == "N"


@responses.activate
def test_no_school_event_refuses_to_delete_existing_lessons():
    # Marking a day no-school deletes its lessons permanently; deleting the
    # event afterwards does not bring them back.
    stub(
        "/getLessonsEvents",
        saved_lesson(
            date="09/07/2026",
            className="Math",
            lessonId=99,
            lessonTitle="Place value",
        ),
    )
    with pytest.raises(UsageError, match="destroys 1 lesson, permanently"):
        create_event(
            PlanbookClient("t.t.t"), title="Holiday", date="09/07/2026", no_school=True
        )


@responses.activate
def test_no_school_event_allowed_with_yes():
    # --yes must bypass the guard AND actually send noSchool=true; the old
    # test only checked ok, so it would have passed even if it did nothing.
    stub("/getLessonsEvents", lesson_days())
    # Empty before the write, one event after: the id-diff must find it.
    stub("/getEvents", event_list())
    stub("/getEvents", event_list(event_record(eventId=555, eventTitle="Holiday")))
    stub("/addEvent", event_list())
    result = create_event(
        PlanbookClient("t.t.t"),
        title="Holiday",
        date="09/07/2026",
        no_school=True,
        confirmed=True,
    )
    assert result["ok"] is True
    sent = dict(
        urllib.parse.parse_qsl(
            [c for c in responses.calls if c.request.url.endswith("/addEvent")][
                -1
            ].request.body
        )
    )
    assert sent["noSchool"] == "true"
    assert sent["updatedFields"] == "extraDays"
    assert result["id"] == 555


@responses.activate
def test_no_school_event_blocked_without_yes_when_lessons_exist():
    # The guard must fire before /addEvent is called, or lessons are lost.
    stub(
        "/getLessonsEvents",
        saved_lesson(date="09/07/2026", className="Math", lessonId=9),
    )
    with pytest.raises(UsageError):
        create_event(
            PlanbookClient("t.t.t"), title="Holiday", date="09/07/2026", no_school=True
        )
    assert not [c for c in responses.calls if c.request.url.endswith("/addEvent")]
