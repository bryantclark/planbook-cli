"""The lesson resource: payloads, sections, links, and the week view."""

import json
import urllib.parse

import pytest
import responses

from conftest import (
    event_list,
    event_record,
    lesson_day,
    lesson_days,
    lesson_record,
    saved_lesson,
    stub,
)
from planbook.client import PlanbookClient
from planbook.errors import UsageError
from planbook.resources.lessons import (
    delete_lesson,
    find_lesson,
    lesson_payload,
    lesson_sections,
    lessons_between,
    no_school_dates,
    read_week,
    resolve_section,
    set_lesson,
)


def test_set_lesson_dry_run_builds_payload_without_network():
    result = lesson_payload(
        class_id=123,
        date="09/03/2026",
        title="Photosynthesis",
        text="<p>Light reactions.</p>",
    )
    assert len(responses.calls) == 0
    payload = result[0]
    for key in ["unitId", "extraLesson", "lessonId", "linkedLessonId"]:
        assert payload[key] == "0"
    assert payload["lessonLock"] == "N"
    assert payload["isEditingALinkedLesson"] == "N"
    assert payload["strategySent"] == "Y"
    assert payload["unitStandardsSent"] == "Y"
    assert payload["statusesSent"] == "Y"
    # Absent unless the caller named assignments: sending "[]" detaches
    # whatever the lesson already had.
    assert "schoolWorks" not in payload
    assert payload["fetchDay"] == "true"


def test_set_lesson_requires_at_least_one_content_field():
    with pytest.raises(UsageError):
        lesson_payload(class_id=123, date="09/03/2026")


def test_set_lesson_updated_fields_are_ordered_and_uppercase():
    result = lesson_payload(class_id=123, date="09/03/2026", title="Title", text="Text")
    assert result[0]["updatedFields"] == "LESSONTITLE,LESSONTEXT"


def test_lesson_payload_never_sets_a_custom_time():
    # The server ignores customStart/customEnd on /updateLesson - a lesson
    # always keeps its class period's times - so the CLI does not offer them.
    payload = lesson_payload(class_id=1, date="09/01/2026", title="T")[0]
    assert payload["customStart"] == ""
    assert payload["customEnd"] == ""
    assert "CUSTOMSTART" not in payload["updatedFields"]


def test_resolve_section_by_number_and_label():
    sections = [
        {"section": 1, "label": "Lesson"},
        {"section": 4, "label": "Objectives"},
    ]
    assert resolve_section(sections, "4") == 4
    assert resolve_section(sections, "Objectives") == 4
    assert resolve_section(sections, "objectives") == 4
    with pytest.raises(UsageError):
        resolve_section(sections, "Nope")
    with pytest.raises(UsageError):
        resolve_section(sections, "9")


def test_set_lesson_writes_arbitrary_sections():
    payload = lesson_payload(class_id=1, date="09/01/2026", sections={1: "a", 4: "b"})[
        0
    ]
    assert payload["lessonText"] == "a"
    assert payload["tab4Text"] == "b"
    assert "TAB4TEXT" in payload["updatedFields"]


def test_lesson_payload_rejects_a_write_that_names_nothing():
    with pytest.raises(UsageError):
        lesson_payload(class_id=1, date="09/01/2026")


@responses.activate
def test_no_school_dates_never_raises():
    # Advisory: a failed lookup must not stop the write it annotates.
    stub("/getEvents", {"error": "true", "msg": "nope"})
    assert no_school_dates(PlanbookClient("t.t.t")) == set()


@responses.activate
def test_no_school_dates_collects_marked_days():
    stub(
        "/getEvents",
        event_list(
            event_record(eventId=1, eventDate="09/07/2026", noSchool=True),
            event_record(eventId=2, eventDate="09/08/2026", noSchool=False),
        ),
    )
    assert no_school_dates(PlanbookClient("t.t.t")) == {"09/07/2026"}


@responses.activate
def test_no_school_dates_reads_y_and_n_rather_than_testing_truthiness():
    # "N" is truthy in Python, so every event date would be called no-school
    # and the warning would fire on every write.
    stub(
        "/getEvents",
        event_list(
            event_record(eventId=1, eventDate="09/07/2026", noSchool="N"),
            event_record(eventId=2, eventDate="09/08/2026", noSchool="Y"),
        ),
    )
    assert no_school_dates(PlanbookClient("t.t.t")) == {"09/08/2026"}


def test_standards_go_as_repeated_fields_not_a_comma_list():
    # A comma-joined value is accepted and clears the set instead of adding.
    payload = lesson_payload(
        class_id=1, date="09/01/2026", standards=["118071", "118072"]
    )[0]
    assert payload["standardDBIds"] == ["118071", "118072"]
    assert "STANDARDS" in payload["updatedFields"]


def test_empty_standards_list_clears_rather_than_omits():
    payload = lesson_payload(class_id=1, date="09/01/2026", standards=[])[0]
    assert payload["standardDBIds"] == [""]


def test_assignments_become_schoolworks_entries():
    payload = lesson_payload(class_id=1, date="09/01/2026", assignments=[42])[0]
    assert json.loads(payload["schoolWorks"]) == [
        {"type": "ASSIGNMENT", "typeId": 42, "shortValueText": "", "longValueText": 0}
    ]


def test_attachments_go_as_repeated_triples():
    payload = lesson_payload(
        class_id=1,
        date="09/01/2026",
        attach=[
            {"name": "a.pdf", "url": "https://s3/a"},
            {"name": "b.pdf", "url": "https://s3/b"},
        ],
    )[0]
    assert payload["attachmentNames"] == ["a.pdf", "b.pdf"]
    assert payload["attachmentURL"] == ["https://s3/a", "https://s3/b"]
    assert payload["attachmentPrivate"] == ["N", "N"]
    assert "ATTACHMENTS" in payload["updatedFields"]


def test_empty_attach_list_clears():
    payload = lesson_payload(class_id=1, date="09/01/2026", attach=[])[0]
    assert payload["attachmentNames"] == [""]


@responses.activate
def test_read_week_dates_come_from_the_day_not_the_lesson():
    # Lessons carry no date of their own.
    stub(
        "/getLessonsEvents",
        lesson_days(
            lesson_day(
                "09/07/2026",
                lesson_record(className="Math", lessonTitle="T", startTime="9:00 AM"),
                {"classId": 2, "className": "Art"},  # no lessonId: unsaved
                dayOfWeek="Monday",
            )
        ),
    )
    week = read_week(PlanbookClient("t.t.t"), monday="09/07/2026")
    assert week[0]["date"] == "09/07/2026"
    assert [x["class_name"] for x in week[0]["lessons"]] == ["Math"]


@responses.activate
def test_lessons_between_spans_a_year_boundary():
    # MM/DD/YYYY compared as strings inverts across New Year, which silently
    # disarmed the no-school guard for exactly the events that span one.
    stub(
        "/getLessonsEvents",
        lesson_days(
            lesson_day("12/22/2026", lesson_record(className="Math", lessonId=5)),
            lesson_day("01/05/2027", lesson_record(className="Math", lessonId=6)),
        ),
    )
    found = lessons_between(
        PlanbookClient("t.t.t"), start="12/22/2026", end="01/05/2027"
    )
    assert len(found) == 2


@responses.activate
def test_delete_lesson_posts_the_right_body():
    stub("/deleteLesson", {"ok": True})
    # The read-back that proves the delete took: no lesson on that date after.
    stub("/getLessonsEvents", lesson_days())
    delete_lesson(PlanbookClient("t.t.t"), class_id=7, date="09/01/2026")
    sent = dict(urllib.parse.parse_qsl(responses.calls[0].request.body))
    assert sent == {"classId": "7", "customDate": "09/01/2026", "userMode": "T"}


@responses.activate
def test_set_lesson_carries_over_text_it_was_not_asked_to_change():
    # updatedFields is NOT a mask: a field sent empty is written empty, so a
    # standards-only write used to wipe the title, body and homework.
    stub(
        "/getLessonsEvents",
        saved_lesson(
            date="09/01/2026",
            lessonId=9,
            lessonTitle="Keep me",
            lessonText="<p>body</p>",
            homeworkText="hw",
            notesText="notes",
        ),
    )
    stub("/updateLesson", {"ok": True})
    # The read-back that proves the standard attached.
    stub(
        "/getLessonsEvents",
        saved_lesson(date="09/01/2026", lessonId=9, standards=[{"id": "3.NBT.A.1"}]),
    )
    set_lesson(
        PlanbookClient("t.t.t"), class_id=1, date="09/01/2026", standards=["118071"]
    )
    write = [c for c in responses.calls if c.request.url.endswith("/updateLesson")][-1]
    sent = dict(urllib.parse.parse_qsl(write.request.body))
    assert sent["lessonTitle"] == "Keep me"
    assert sent["lessonText"] == "<p>body</p>"
    assert sent["homeworkText"] == "hw"
    assert sent["notesText"] == "notes"


def test_lesson_payload_validates_the_date():
    # Bulk items never pass through argparse, so the check lives here too.
    with pytest.raises(UsageError):
        lesson_payload(class_id=1, date="13/45/2026", title="T")


def test_lesson_payload_only_sends_schoolworks_when_assignments_are_named():
    # A rename used to send schoolWorks="[]", silently detaching every
    # assignment on the lesson.
    bare = lesson_payload(class_id=1, date="09/01/2026", title="Renamed")[0]
    assert "schoolWorks" not in bare
    named = lesson_payload(class_id=1, date="09/01/2026", assignments=[42])[0]
    assert '"typeId":42' in named["schoolWorks"]
    cleared = lesson_payload(class_id=1, date="09/01/2026", assignments=[])[0]
    assert cleared["schoolWorks"] == "[]"


@responses.activate
def test_find_lesson_matches_an_unpadded_date_against_the_server_form():
    # A bulk item's "9/3/2026" must find the lesson saved on "09/03/2026",
    # not miss it and overwrite the record blank.
    stub("/getLessonsEvents", saved_lesson(lessonId=9, lessonTitle="Keep"))
    found = find_lesson(PlanbookClient("t.t.t"), class_id=1, date="9/3/2026")
    assert found is not None
    assert found["lessonTitle"] == "Keep"


def _sections(conf):
    stub("/getSettings", conf)
    return {s["section"]: s for s in lesson_sections(PlanbookClient("t.t.t"))}


@responses.activate
def test_an_absent_tab_enabled_flag_means_enabled():
    # Older accounts answer without the key at all.
    assert _sections({"tab4Label": "Standards"})[4]["enabled"] is True


@responses.activate
def test_the_wire_forms_of_a_disabled_tab_all_read_as_disabled():
    conf = {f"tab{i}Enabled": v for i, v in ((4, "N"), (5, False), (6, 0))}
    sections = _sections(conf)
    assert [sections[i]["enabled"] for i in (4, 5, 6)] == [False, False, False]


@responses.activate
def test_an_empty_tab_enabled_flag_means_enabled():
    # The server writes "" for a tab nobody has touched, and those tabs show
    # up in the layout.
    assert _sections({"tab4Enabled": ""})[4]["enabled"] is True
