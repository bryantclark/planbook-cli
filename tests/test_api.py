import json
import urllib.parse

import pytest
import responses

from planbook import api
from planbook.client import API_BASE, PlanbookClient
from planbook.errors import SchemaDrift, UsageError


def class_wire_record(teach_days=("m", "t", "w", "r", "f")):
    """A class record in wire format. Teach flags are "Y"/"N" strings."""
    raw = {"cId": 123, "cN": "Biology", "cSd": "08/31/2026", "cEd": "06/06/2027"}
    for prefix in ["m", "t", "w", "r", "f", "s", "u"]:
        raw[f"{prefix}T"] = "Y" if prefix in teach_days else "N"
        raw[f"{prefix}St"] = f"{prefix}-start"
        raw[f"{prefix}Et"] = f"{prefix}-end"
    return raw


def _schedule_row(teach=(), start_times=None, end_times=None, **extra):
    """One classSchedule row as /getClass returns it: 20 Sunday-indexed slots."""
    row = {"scheduleStart": "08/31/2026", "additionalClassDays": [], "scheduleId": 9}
    for n in range(1, 21):
        row[f"day{n}Teach"] = n in teach
        row[f"day{n}StartTime"] = (start_times or {}).get(n, "")
        row[f"day{n}EndTime"] = (end_times or {}).get(n, "")
    row.update(extra)
    return row


def test_parse_days_weekdays_and_special_letters():
    assert api.parse_days("MTWRF") == [
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
    ]
    assert api.parse_days("RU") == ["thursday", "sunday"]


def test_parse_days_rejects_unknown_letter():
    with pytest.raises(UsageError):
        api.parse_days("X")


def test_normalize_class_maps_fields_and_all_day_schedule():
    result = api.normalize_class(class_wire_record())
    assert result["id"] == 123
    assert result["name"] == "Biology"
    assert set(result["schedule"]) == {
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    }
    assert result["schedule"]["thursday"] == {
        "teaches": True,
        "start": "r-start",
        "end": "r-end",
    }
    assert result["schedule"]["sunday"] == {
        "teaches": False,
        "start": "u-start",
        "end": "u-end",
    }


def test_normalize_class_turns_yn_flags_into_booleans():
    # "N" is truthy in Python; passed through it would read as "teaches".
    result = api.normalize_class(class_wire_record(teach_days=("m", "w", "f")))
    teaching = [d for d, v in result["schedule"].items() if v["teaches"]]
    assert teaching == ["monday", "wednesday", "friday"]


def test_build_schedule_indexes_from_sunday():
    # teachDay1 is Sunday, not Monday; an off-by-one silently shifts every day.
    slot = json.loads(
        api.build_schedule(["monday", "wednesday", "friday"], "08/31/2026")
    )[0]
    assert slot["teachDay1"] is False  # Sunday
    assert slot["teachDay2"] is True  # Monday
    assert slot["teachDay4"] is True  # Wednesday
    assert slot["teachDay6"] is True  # Friday
    assert slot["teachDay7"] is False  # Saturday
    assert slot["scheduleStart"] == "08/31/2026"


@responses.activate
def test_update_class_preserves_fields_it_was_not_asked_to_change():
    # The endpoint replaces the whole record, so a rename must not blank the
    # description, colour, layout or per-day times.
    responses.post(
        f"{API_BASE}/getClass",
        json={
            "classId": 5,
            "className": "Bio",
            "classStartDate": "08/31/2026",
            "classEndDate": "06/06/2027",
            "color": "#FF00FF",
            "classDesc": "keep me",
            "titleColor": "#111111",
            "titleSize": "14",
            "titleFont": "Georgia",
            "lessonLayoutId": 77,
            "noStudents": True,
            "useSchoolStart": "N",
            "useSchoolEnd": "N",
            "classLabelBold": True,
            "classLabelItalic": False,
            "classLabelUnderline": False,
            "source": "",
            "sourceId": "0",
            "collaborateType": 0,
            "collaborateSubjectId": 0,
            "collaborateKey": "",
            "mondayTeach": "Y",
            "tuesdayTeach": "N",
            "wednesdayTeach": "Y",
            "thursdayTeach": "N",
            "fridayTeach": "Y",
            "saturdayTeach": "N",
            "sundayTeach": "N",
            "mondayStartTime": "09:00",
            "mondayEndTime": "10:00",
            "classSchedule": [
                _schedule_row(teach=(2, 4, 6), start_times={2: "9:00 AM"})
            ],
        },
    )
    responses.post(f"{API_BASE}/updateClass/v10", json={})

    api.update_class(PlanbookClient("t.t.t"), class_id=5, name="Bio 2")

    sent = dict(urllib.parse.parse_qsl(responses.calls[1].request.body))
    assert sent["className"] == "Bio 2"
    assert sent["classDesc"] == "keep me"
    assert sent["color"] == "#FF00FF"
    assert sent["lessonLayoutId"] == "77"
    assert sent["titleFont"] == "Georgia"
    # schedule survives untouched, times included
    assert [sent[f"{d}Teach"] for d in ("monday", "wednesday", "friday")] == ["Y"] * 3
    assert sent["tuesdayTeach"] == "N"
    assert json.loads(sent["schedules"])[0]["startDay2"] == "9:00 AM"
    # and the flags that make the write actually land
    assert sent["scheduleChange"] == "true"
    assert sent["verifyShift"] == "false"


@responses.activate
def test_update_class_replaces_schedule_when_days_given():
    responses.post(
        f"{API_BASE}/getClass",
        json={
            "classId": 5,
            "className": "Bio",
            "classStartDate": "08/31/2026",
            "classEndDate": "06/06/2027",
            "mondayTeach": "Y",
            "wednesdayTeach": "Y",
            "fridayTeach": "Y",
            "tuesdayTeach": "N",
            "thursdayTeach": "N",
            "saturdayTeach": "N",
            "sundayTeach": "N",
            "classSchedule": [_schedule_row(teach=(2, 4, 6))],
        },
    )
    responses.post(f"{API_BASE}/updateClass/v10", json={})
    api.update_class(PlanbookClient("t.t.t"), class_id=5, days=["tuesday", "thursday"])
    sent = dict(urllib.parse.parse_qsl(responses.calls[1].request.body))
    assert sent["mondayTeach"] == "N" and sent["tuesdayTeach"] == "Y"


def test_class_payload_uses_yn_not_true_false():
    # true/false is accepted and silently produces a class teaching no days.
    payload = api.create_class(
        None,
        name="X",
        start_date="08/31/2026",
        end_date="06/06/2027",
        days=["monday"],
        dry_run=True,
    )["payload"]
    assert payload["mondayTeach"] == "Y"
    assert payload["tuesdayTeach"] == "N"
    assert payload["verifyShift"] == "false"


def test_event_payload_commits_rather_than_only_validating():
    # verifyShift="true" answers exactly like success and writes nothing.
    payload = api.create_event(None, title="X", date="09/15/2026", dry_run=True)[
        "payload"
    ]
    assert payload["verifyShift"] == "false"
    assert payload["eventCurrentDate"] == ""
    assert payload["shiftLessons"] == "N"


def test_unit_payload_sends_class_id_as_subject_id():
    payload = api.create_unit(None, class_id=99, number="U1", title="T", dry_run=True)[
        "payload"
    ]
    assert payload["subjectId"] == "99"
    assert payload["action"] == "A"


def test_delete_lesson_payload():
    payload = api.delete_lesson(None, class_id=7, date="09/01/2026", dry_run=True)[
        "payload"
    ]
    assert payload == {"classId": "7", "customDate": "09/01/2026", "userMode": "T"}


@responses.activate
def test_set_lesson_dry_run_builds_payload_without_network():
    result = api.set_lesson(
        None,
        class_id=123,
        date="09/03/2026",
        title="Photosynthesis",
        text="<p>Light reactions.</p>",
        dry_run=True,
    )
    assert len(responses.calls) == 0
    payload = result["payload"]
    for key in ["unitId", "extraLesson", "lessonId", "linkedLessonId"]:
        assert payload[key] == "0"
    assert payload["lessonLock"] == "N"
    assert payload["isEditingALinkedLesson"] == "N"
    assert payload["strategySent"] == "Y"
    assert payload["unitStandardsSent"] == "Y"
    assert payload["statusesSent"] == "Y"
    assert payload["schoolWorks"] == "[]"
    assert payload["fetchDay"] == "true"


def test_set_lesson_requires_at_least_one_content_field():
    with pytest.raises(UsageError):
        api.set_lesson(None, class_id=123, date="09/03/2026", dry_run=True)


def test_set_lesson_updated_fields_are_ordered_and_uppercase():
    result = api.set_lesson(
        None,
        class_id=123,
        date="09/03/2026",
        title="Title",
        text="Text",
        dry_run=True,
    )
    assert result["payload"]["updatedFields"] == "LESSONTITLE,LESSONTEXT"


@responses.activate
def test_list_classes_normalizes_and_raw_returns_untouched_body():
    body = {
        "currentYearId": 99,
        "classes": [class_wire_record()],
        "lessonBanks": [{"id": 1}],
        "districtLessonBanks": [{"id": 2}],
    }
    responses.post(f"{API_BASE}/getClasses2", json=body)
    responses.post(f"{API_BASE}/getClasses2", json=body)
    client = PlanbookClient("cookie")

    mapped = api.list_classes(client)
    raw = api.list_classes(client, raw=True)

    assert mapped["current_year_id"] == 99
    assert mapped["classes"][0]["id"] == 123
    assert mapped["lesson_banks"] == [{"id": 1}]
    assert mapped["district_lesson_banks"] == [{"id": 2}]
    assert raw is not body
    assert raw == body


@responses.activate
def test_list_classes_raises_schema_drift_without_classes_key():
    responses.post(f"{API_BASE}/getClasses2", json={"currentYearId": 99})
    with pytest.raises(SchemaDrift):
        api.list_classes(PlanbookClient("cookie"))


def test_parse_time_accepts_24h_and_12h():
    # Planbook stores only 12-hour times; a 24-hour string is accepted on the
    # wire and stored as empty, silently losing the time.
    assert api.parse_time("14:30") == "2:30 PM"
    assert api.parse_time("09:00") == "9:00 AM"
    assert api.parse_time("9:00am") == "9:00 AM"
    assert api.parse_time("9:00 AM") == "9:00 AM"
    assert api.parse_time("") == ""
    assert api.parse_time(None) == ""


def test_parse_time_handles_noon_and_midnight():
    assert api.parse_time("12:00") == "12:00 PM"
    assert api.parse_time("00:15") == "12:15 AM"
    assert api.parse_time("12:00 AM") == "12:00 AM"


def test_parse_time_rejects_nonsense():
    for bad in ("9:5", "25:00", "10:99", "lunchtime"):
        with pytest.raises(UsageError):
            api.parse_time(bad)


def test_parse_day_times_whole_week_and_per_day():
    assert api.parse_day_times(["9:00-9:50"], ["monday", "friday"]) == {
        "monday": ("9:00 AM", "9:50 AM"),
        "friday": ("9:00 AM", "9:50 AM"),
    }
    assert api.parse_day_times(["M=8:00-8:45", "W=13:00-13:50"], []) == {
        "monday": ("8:00 AM", "8:45 AM"),
        "wednesday": ("1:00 PM", "1:50 PM"),
    }


def test_set_lesson_normalizes_times_and_marks_them_updated():
    payload = api.set_lesson(
        None,
        class_id=1,
        date="09/01/2026",
        start_time="14:30",
        end_time="15:20",
        dry_run=True,
    )["payload"]
    assert payload["customStart"] == "2:30 PM"
    assert payload["customEnd"] == "3:20 PM"
    assert "CUSTOMSTART" in payload["updatedFields"]


def test_build_schedule_carries_per_day_times():
    slot = json.loads(
        api.build_schedule(["monday"], "08/31/2026", {"monday": ("9:00 AM", "9:50 AM")})
    )[0]
    assert slot["startDay2"] == "9:00 AM"  # teachDay2 is Monday
    assert slot["endDay2"] == "9:50 AM"
    assert slot["startDay3"] == ""  # Tuesday, not taught


def test_resolve_section_by_number_and_label():
    sections = [
        {"section": 1, "label": "Lesson"},
        {"section": 4, "label": "Objectives"},
    ]
    assert api.resolve_section(sections, "4") == 4
    assert api.resolve_section(sections, "Objectives") == 4
    assert api.resolve_section(sections, "objectives") == 4
    with pytest.raises(UsageError):
        api.resolve_section(sections, "Nope")
    with pytest.raises(UsageError):
        api.resolve_section(sections, "9")


def test_set_lesson_writes_arbitrary_sections():
    payload = api.set_lesson(
        None, class_id=1, date="09/01/2026", sections={1: "a", 4: "b"}, dry_run=True
    )["payload"]
    assert payload["lessonText"] == "a"
    assert payload["tab4Text"] == "b"
    assert "TAB4TEXT" in payload["updatedFields"]


@responses.activate
def test_update_class_preserves_rotation_slots_beyond_the_week():
    # A 10-day rotation must survive a rename. Rebuilding from a blank
    # template would flatten it into an ordinary week, silently.
    responses.post(
        f"{API_BASE}/getClass",
        json={
            "className": "Bio",
            "classStartDate": "08/31/2026",
            "classEndDate": "06/06/2027",
            "classSchedule": [
                _schedule_row(
                    teach=(2, 9, 10),
                    start_times={9: "1:00 PM"},
                    additionalClassDays=[{"x": 1}],
                )
            ],
        },
    )
    responses.post(f"{API_BASE}/updateClass/v10", json={})
    api.update_class(PlanbookClient("t.t.t"), class_id=5, name="Bio 2")
    slot = json.loads(
        dict(urllib.parse.parse_qsl(responses.calls[1].request.body))["schedules"]
    )[0]
    assert slot["teachDay9"] is True and slot["teachDay10"] is True
    assert slot["startDay9"] == "1:00 PM"
    assert slot["additionalClassDays"] == [{"x": 1}]
    assert slot["scheduleId"] == 9


@responses.activate
def test_update_class_refuses_a_response_without_a_schedule():
    # Coercing a missing schedule to defaults would zero the teaching days.
    responses.post(f"{API_BASE}/getClass", json={"className": "Bio"})
    with pytest.raises(SchemaDrift):
        api.update_class(PlanbookClient("t.t.t"), class_id=5, name="Bio 2")


@responses.activate
def test_update_class_keeps_earlier_schedule_rows_untouched():
    responses.post(
        f"{API_BASE}/getClass",
        json={
            "className": "Bio",
            "classStartDate": "08/31/2026",
            "classSchedule": [
                _schedule_row(teach=(2,), scheduleStart="08/31/2026"),
                _schedule_row(teach=(4,), scheduleStart="01/05/2027"),
            ],
        },
    )
    responses.post(f"{API_BASE}/updateClass/v10", json={})
    api.update_class(PlanbookClient("t.t.t"), class_id=5, days=["friday"])
    rows = json.loads(
        dict(urllib.parse.parse_qsl(responses.calls[1].request.body))["schedules"]
    )
    assert rows[0]["teachDay2"] is True  # history untouched
    assert rows[1]["teachDay6"] is True  # newest row edited to Friday
    assert rows[1]["teachDay4"] is False


def test_set_lesson_requires_both_times_together():
    with pytest.raises(UsageError):
        api.set_lesson(
            None, class_id=1, date="09/01/2026", start_time="9:00", dry_run=True
        )


@responses.activate
def test_no_school_dates_never_raises():
    # Advisory: a failed lookup must not stop the write it annotates.
    responses.post(f"{API_BASE}/getEvents", json={"error": "true", "msg": "nope"})
    assert api.no_school_dates(PlanbookClient("t.t.t")) == set()


@responses.activate
def test_no_school_dates_collects_marked_days():
    responses.post(
        f"{API_BASE}/getEvents",
        json={
            "events": [
                {"eventId": 1, "eventDate": "09/07/2026", "noSchool": True},
                {"eventId": 2, "eventDate": "09/08/2026", "noSchool": False},
            ]
        },
    )
    assert api.no_school_dates(PlanbookClient("t.t.t")) == {"09/07/2026"}


def test_standards_go_as_repeated_fields_not_a_comma_list():
    # A comma-joined value is accepted and clears the set instead of adding.
    payload = api.set_lesson(
        None,
        class_id=1,
        date="09/01/2026",
        standards=["118071", "118072"],
        dry_run=True,
    )["payload"]
    assert payload["standardDBIds"] == ["118071", "118072"]
    assert "STANDARDS" in payload["updatedFields"]


def test_empty_standards_list_clears_rather_than_omits():
    payload = api.set_lesson(
        None, class_id=1, date="09/01/2026", standards=[], dry_run=True
    )["payload"]
    assert payload["standardDBIds"] == [""]


def test_assignments_become_schoolworks_entries():
    payload = api.set_lesson(
        None, class_id=1, date="09/01/2026", assignments=[42], dry_run=True
    )["payload"]
    assert json.loads(payload["schoolWorks"]) == [
        {"type": "ASSIGNMENT", "typeId": 42, "shortValueText": "", "longValueText": 0}
    ]


def test_attachments_go_as_repeated_triples():
    payload = api.set_lesson(
        None,
        class_id=1,
        date="09/01/2026",
        attach=[
            {"name": "a.pdf", "url": "https://s3/a"},
            {"name": "b.pdf", "url": "https://s3/b"},
        ],
        dry_run=True,
    )["payload"]
    assert payload["attachmentNames"] == ["a.pdf", "b.pdf"]
    assert payload["attachmentURL"] == ["https://s3/a", "https://s3/b"]
    assert payload["attachmentPrivate"] == ["N", "N"]
    assert "ATTACHMENTS" in payload["updatedFields"]


def test_empty_attach_list_clears():
    payload = api.set_lesson(
        None, class_id=1, date="09/01/2026", attach=[], dry_run=True
    )["payload"]
    assert payload["attachmentNames"] == [""]


@responses.activate
def test_no_school_event_refuses_to_delete_existing_lessons():
    # Marking a day no-school deletes its lessons permanently; deleting the
    # event afterwards does not bring them back.
    responses.post(f"{API_BASE}/getLessonsEvents", json={"days": [
        {"date": "09/07/2026", "dayOfWeek": "Monday", "objects": [
            {"classId": 1, "className": "Math", "lessonId": 99,
             "lessonTitle": "Place value"},
        ]},
    ]})
    with pytest.raises(UsageError, match="deletes them permanently"):
        api.create_event(PlanbookClient("t.t.t"), title="Holiday",
                         date="09/07/2026", no_school=True)


@responses.activate
def test_no_school_event_allowed_with_force():
    responses.post(f"{API_BASE}/getLessonsEvents", json={"days": []})
    responses.post(f"{API_BASE}/addEvent", json={"events": []})
    result = api.create_event(PlanbookClient("t.t.t"), title="Holiday",
                              date="09/07/2026", no_school=True, force=True)
    assert result["ok"] is True


@responses.activate
def test_read_week_dates_come_from_the_day_not_the_lesson():
    # Lessons carry no date of their own.
    responses.post(f"{API_BASE}/getLessonsEvents", json={"days": [
        {"date": "09/07/2026", "dayOfWeek": "Monday", "objects": [
            {"classId": 1, "className": "Math", "lessonId": 5,
             "lessonTitle": "T", "startTime": "9:00 AM"},
            {"classId": 2, "className": "Art"},          # no lessonId: unsaved
        ]},
    ]})
    week = api.read_week(PlanbookClient("t.t.t"), monday="09/07/2026")
    assert week[0]["date"] == "09/07/2026"
    assert [x["class_name"] for x in week[0]["lessons"]] == ["Math"]
