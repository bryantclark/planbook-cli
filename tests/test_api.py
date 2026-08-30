import json
import urllib.parse

import pytest
import responses

from planbook import api
from planbook.client import API_BASE, PlanbookClient
from planbook.errors import ApiError, SchemaDrift, UsageError


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
    payload = api.class_payload(
        name="X", start_date="08/31/2026", end_date="06/06/2027", days=["monday"]
    )
    assert payload["mondayTeach"] == "Y"
    assert payload["tuesdayTeach"] == "N"
    assert payload["verifyShift"] == "false"


def test_event_payload_commits_rather_than_only_validating():
    # verifyShift="true" answers exactly like success and writes nothing.
    payload = api.event_payload(
        {"eventTitle": "X", "eventDate": "09/15/2026", "endDate": "09/15/2026"}
    )
    assert payload["verifyShift"] == "false"
    assert payload["eventCurrentDate"] == ""
    assert payload["shiftLessons"] == "N"


def test_unit_payload_sends_class_id_as_subject_id():
    payload = api.unit_payload(action="A", class_id=99, number="U1", title="T")
    assert payload["subjectId"] == "99"
    assert payload["action"] == "A"


def test_set_lesson_dry_run_builds_payload_without_network():
    result = api.lesson_payload(
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
        api.lesson_payload(class_id=123, date="09/03/2026")


def test_set_lesson_updated_fields_are_ordered_and_uppercase():
    result = api.lesson_payload(
        class_id=123, date="09/03/2026", title="Title", text="Text"
    )
    assert result[0]["updatedFields"] == "LESSONTITLE,LESSONTEXT"


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


def test_lesson_payload_never_sets_a_custom_time():
    # The server ignores customStart/customEnd on /updateLesson - a lesson
    # always keeps its class period's times - so the CLI does not offer them.
    payload = api.lesson_payload(class_id=1, date="09/01/2026", title="T")[0]
    assert payload["customStart"] == ""
    assert payload["customEnd"] == ""
    assert "CUSTOMSTART" not in payload["updatedFields"]


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
    payload = api.lesson_payload(
        class_id=1, date="09/01/2026", sections={1: "a", 4: "b"}
    )[0]
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


def test_lesson_payload_rejects_a_write_that_names_nothing():
    with pytest.raises(UsageError):
        api.lesson_payload(class_id=1, date="09/01/2026")


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
    payload = api.lesson_payload(
        class_id=1, date="09/01/2026", standards=["118071", "118072"]
    )[0]
    assert payload["standardDBIds"] == ["118071", "118072"]
    assert "STANDARDS" in payload["updatedFields"]


def test_empty_standards_list_clears_rather_than_omits():
    payload = api.lesson_payload(class_id=1, date="09/01/2026", standards=[])[0]
    assert payload["standardDBIds"] == [""]


def test_assignments_become_schoolworks_entries():
    payload = api.lesson_payload(class_id=1, date="09/01/2026", assignments=[42])[0]
    assert json.loads(payload["schoolWorks"]) == [
        {"type": "ASSIGNMENT", "typeId": 42, "shortValueText": "", "longValueText": 0}
    ]


def test_attachments_go_as_repeated_triples():
    payload = api.lesson_payload(
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
    payload = api.lesson_payload(class_id=1, date="09/01/2026", attach=[])[0]
    assert payload["attachmentNames"] == [""]


@responses.activate
def test_no_school_event_refuses_to_delete_existing_lessons():
    # Marking a day no-school deletes its lessons permanently; deleting the
    # event afterwards does not bring them back.
    responses.post(
        f"{API_BASE}/getLessonsEvents",
        json={
            "days": [
                {
                    "date": "09/07/2026",
                    "dayOfWeek": "Monday",
                    "objects": [
                        {
                            "classId": 1,
                            "className": "Math",
                            "lessonId": 99,
                            "lessonTitle": "Place value",
                        },
                    ],
                },
            ]
        },
    )
    with pytest.raises(UsageError, match="deletes them permanently"):
        api.create_event(
            PlanbookClient("t.t.t"), title="Holiday", date="09/07/2026", no_school=True
        )


@responses.activate
def test_no_school_event_allowed_with_force():
    # --force must bypass the guard AND actually send noSchool=true; the old
    # test only checked ok, so it would have passed even if force did nothing.
    responses.post(f"{API_BASE}/getLessonsEvents", json={"days": []})
    # Empty before the write, one event after: the id-diff must find it.
    responses.add(responses.POST, f"{API_BASE}/getEvents", json={"events": []})
    responses.add(
        responses.POST,
        f"{API_BASE}/getEvents",
        json={"events": [{"eventId": 555, "eventTitle": "Holiday"}]},
    )
    responses.post(f"{API_BASE}/addEvent", json={"events": []})
    result = api.create_event(
        PlanbookClient("t.t.t"),
        title="Holiday",
        date="09/07/2026",
        no_school=True,
        force=True,
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
    assert result["event_id"] == 555


@responses.activate
def test_no_school_event_blocked_without_force_when_lessons_exist():
    # The guard must fire before /addEvent is called, or lessons are lost.
    responses.post(
        f"{API_BASE}/getLessonsEvents",
        json={
            "days": [
                {
                    "date": "09/07/2026",
                    "objects": [{"classId": 1, "className": "Math", "lessonId": 9}],
                }
            ]
        },
    )
    with pytest.raises(UsageError):
        api.create_event(
            PlanbookClient("t.t.t"), title="Holiday", date="09/07/2026", no_school=True
        )
    assert not [c for c in responses.calls if c.request.url.endswith("/addEvent")]


@responses.activate
def test_read_week_dates_come_from_the_day_not_the_lesson():
    # Lessons carry no date of their own.
    responses.post(
        f"{API_BASE}/getLessonsEvents",
        json={
            "days": [
                {
                    "date": "09/07/2026",
                    "dayOfWeek": "Monday",
                    "objects": [
                        {
                            "classId": 1,
                            "className": "Math",
                            "lessonId": 5,
                            "lessonTitle": "T",
                            "startTime": "9:00 AM",
                        },
                        {"classId": 2, "className": "Art"},  # no lessonId: unsaved
                    ],
                },
            ]
        },
    )
    week = api.read_week(PlanbookClient("t.t.t"), monday="09/07/2026")
    assert week[0]["date"] == "09/07/2026"
    assert [x["class_name"] for x in week[0]["lessons"]] == ["Math"]


def test_student_payload_omits_id_when_creating():
    payload = api.student_payload(first_name="Ada", last_name="Lovelace")
    assert "studentId" not in payload
    assert payload["studentFirstName"] == "Ada"
    assert payload["userMode"] == "T"


def test_student_payload_includes_id_when_updating():
    payload = api.student_payload(first_name="Ada", last_name="Lovelace", student_id=7)
    assert payload["studentId"] == "7"


@responses.activate
def test_list_students_normalizes_both_shapes():
    # Account-wide returns {id: "Last, First"}; per-class returns records.
    responses.post(
        f"{API_BASE}/services/planbook/student/getAllFromSchool",
        json={"2139917": "Lovelace, Ada"},
    )
    everyone = api.list_students(PlanbookClient("t.t.t"))
    assert everyone == [
        {"id": 2139917, "name": "Lovelace, Ada", "last_name": "Lovelace"}
    ]

    responses.post(
        f"{API_BASE}/getStudentsServlet",
        json={"students": [{"studentId": 1, "firstName": "Ada", "lastName": "L"}]},
    )
    in_class = api.list_students(PlanbookClient("t.t.t"), class_id=5)
    assert in_class[0]["first_name"] == "Ada"


@responses.activate
def test_list_students_rejects_a_shape_it_does_not_recognise():
    responses.post(f"{API_BASE}/getStudentsServlet", json={"nope": []})
    with pytest.raises(SchemaDrift):
        api.list_students(PlanbookClient("t.t.t"), class_id=5)


@responses.activate
def test_lessons_between_spans_a_year_boundary():
    # MM/DD/YYYY compared as strings inverts across New Year, which silently
    # disarmed the no-school guard for exactly the events that span one.
    responses.post(
        f"{API_BASE}/getLessonsEvents",
        json={
            "days": [
                {
                    "date": "12/22/2026",
                    "dayOfWeek": "Tuesday",
                    "objects": [{"classId": 1, "className": "Math", "lessonId": 5}],
                },
                {
                    "date": "01/05/2027",
                    "dayOfWeek": "Tuesday",
                    "objects": [{"classId": 1, "className": "Math", "lessonId": 6}],
                },
            ]
        },
    )
    found = api.lessons_between(
        PlanbookClient("t.t.t"), start="12/22/2026", end="01/05/2027"
    )
    assert len(found) == 2


@responses.activate
def test_delete_lesson_posts_the_right_body():
    responses.post(f"{API_BASE}/deleteLesson", json={"ok": True})
    api.delete_lesson(PlanbookClient("t.t.t"), class_id=7, date="09/01/2026")
    sent = dict(urllib.parse.parse_qsl(responses.calls[0].request.body))
    assert sent == {"classId": "7", "customDate": "09/01/2026", "userMode": "T"}


@responses.activate
def test_set_lesson_carries_over_text_it_was_not_asked_to_change():
    # updatedFields is NOT a mask: a field sent empty is written empty, so a
    # standards-only write used to wipe the title, body and homework.
    responses.post(
        f"{API_BASE}/getLessonsEvents",
        json={
            "days": [
                {
                    "date": "09/01/2026",
                    "dayOfWeek": "Tuesday",
                    "objects": [
                        {
                            "classId": 1,
                            "className": "Math",
                            "lessonId": 9,
                            "lessonTitle": "Keep me",
                            "lessonText": "<p>body</p>",
                            "homeworkText": "hw",
                            "notesText": "notes",
                        }
                    ],
                }
            ]
        },
    )
    responses.post(f"{API_BASE}/updateLesson", json={"ok": True})
    api.set_lesson(
        PlanbookClient("t.t.t"), class_id=1, date="09/01/2026", standards=["118071"]
    )
    write = [c for c in responses.calls if c.request.url.endswith("/updateLesson")][-1]
    sent = dict(urllib.parse.parse_qsl(write.request.body))
    assert sent["lessonTitle"] == "Keep me"
    assert sent["lessonText"] == "<p>body</p>"
    assert sent["homeworkText"] == "hw"
    assert sent["notesText"] == "notes"


@responses.activate
def test_set_lesson_carries_over_unit_sections_and_flags():
    # A fresh payload resets these to their defaults, so an edit that names
    # only the title used to silently drop the unit, the lock and section 4.
    responses.post(
        f"{API_BASE}/getLessonsEvents",
        json={
            "days": [
                {
                    "date": "09/01/2026",
                    "dayOfWeek": "Tuesday",
                    "objects": [
                        {
                            "classId": 1,
                            "className": "Math",
                            "lessonId": 9,
                            "lessonTitle": "Keep",
                            "lessonText": "<p>b</p>",
                            "startTime": "9:05 AM",
                            "endTime": "9:55 AM",
                            "unitId": 42,
                            "lessonLock": "Y",
                            "extraLesson": 0,
                            "linkedLessonId": 0,
                            "tab4Text": "<p>objectives</p>",
                        }
                    ],
                }
            ]
        },
    )
    responses.post(f"{API_BASE}/updateLesson", json={"ok": True})
    api.set_lesson(
        PlanbookClient("t.t.t"), class_id=1, date="09/01/2026", title="Renamed"
    )
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


def test_parse_date_rejects_what_the_server_answers_with_a_null_pointer():
    # An impossible date used to reach Planbook, which replied with a Java NPE
    # about Schedule.getScheduleStart() - an API error, not a usage error.
    assert api.parse_date("09/03/2026") == "09/03/2026"
    # Zero-padded so it matches the server's format on find_lesson's exact
    # string compare; an unpadded date used to miss the saved lesson and blank
    # it on write.
    assert api.parse_date("9/3/2026") == "09/03/2026"
    assert api.parse_date("12/1/2026") == "12/01/2026"
    for bad in ("13/45/2026", "notadate", "2026-09-03", "09/31/2026", "9/3/26"):
        with pytest.raises(UsageError):
            api.parse_date(bad)


def test_lesson_payload_validates_the_date():
    # Bulk items never pass through argparse, so the check lives here too.
    with pytest.raises(UsageError):
        api.lesson_payload(class_id=1, date="13/45/2026", title="T")


def test_lesson_payload_only_sends_schoolworks_when_assignments_are_named():
    # A rename used to send schoolWorks="[]", silently detaching every
    # assignment on the lesson.
    bare = api.lesson_payload(class_id=1, date="09/01/2026", title="Renamed")[0]
    assert "schoolWorks" not in bare
    named = api.lesson_payload(class_id=1, date="09/01/2026", assignments=[42])[0]
    assert '"typeId":42' in named["schoolWorks"]
    cleared = api.lesson_payload(class_id=1, date="09/01/2026", assignments=[])[0]
    assert cleared["schoolWorks"] == "[]"


@responses.activate
def test_update_todo_carries_over_what_the_caller_did_not_name():
    # /updateToDo replaces the whole record, so a payload built from defaults
    # silently reopened a completed to-do and reset its priority.
    responses.post(
        f"{API_BASE}/getToDos",
        json={
            "toDos": [
                {
                    "toDoId": 7,
                    "toDoText": "Old",
                    "startDate": "09/01/2026",
                    "dueDate": "09/05/2026",
                    "priority": "3",
                    "done": "1",
                    "repeats": "weekly",
                }
            ]
        },
    )
    responses.post(f"{API_BASE}/updateToDo", json={"ok": True})
    api.update_todo(PlanbookClient("t.t.t"), todo_id=7, text="New")
    sent = dict(
        urllib.parse.parse_qsl(
            [c for c in responses.calls if c.request.url.endswith("/updateToDo")][
                -1
            ].request.body
        )
    )
    assert sent["toDoText"] == "New"
    assert sent["dueDate"] == "09/05/2026"
    assert sent["priority"] == "3"
    assert sent["done"] == "1"
    assert sent["repeats"] == "weekly"


@responses.activate
def test_update_unit_carries_over_what_the_caller_did_not_name():
    # /updateUnit replaces the whole record, so renaming a unit used to blank
    # its description, dates and section texts.
    responses.post(
        f"{API_BASE}/getUnits",
        json={
            "units": [
                {
                    "unitId": 5,
                    "unitNum": "U1",
                    "unitTitle": "Old",
                    "unitDesc": "keep me",
                    "unitStart": "09/01/2026",
                    "unitEnd": "09/30/2026",
                    "unitLessonText": "<p>plan</p>",
                }
            ]
        },
    )
    responses.post(f"{API_BASE}/updateUnit", json={"ok": True})
    api.update_unit(PlanbookClient("t.t.t"), unit_id=5, class_id=1, title="New")
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
def test_update_student_carries_over_and_needs_the_class():
    # /updateStudentServlet replaces the whole record, so a rename used to
    # blank the email, phone and parent email the student had on file.
    responses.post(
        f"{API_BASE}/getStudentsServlet",
        json={
            "students": [
                {
                    "studentId": 7,
                    "firstName": "Ada",
                    "lastName": "Lovelace",
                    "emailAddress": "ada@x.z",
                    "phoneNumber": "555-0100",
                    "parentEmailAddress": "parent@x.z",
                }
            ]
        },
    )
    responses.post(f"{API_BASE}/updateStudentServlet", json={"ok": True})
    api.update_student(
        PlanbookClient("t.t.t"), student_id=7, class_id=1, last_name="Byron"
    )
    sent = dict(
        urllib.parse.parse_qsl(
            [
                c
                for c in responses.calls
                if c.request.url.endswith("/updateStudentServlet")
            ][-1].request.body
        )
    )
    assert sent["studentLastName"] == "Byron"
    assert sent["studentFirstName"] == "Ada"
    assert sent["studentEmailAddress"] == "ada@x.z"
    assert sent["studentPhoneNumber"] == "555-0100"
    assert sent["parentEmailAddress"] == "parent@x.z"


@responses.activate
def test_update_student_refuses_when_the_student_is_not_in_the_class():
    responses.post(f"{API_BASE}/getStudentsServlet", json={"students": []})
    with pytest.raises(ApiError):
        api.update_student(PlanbookClient("t.t.t"), student_id=7, class_id=1)


@responses.activate
def test_update_student_carries_over_the_photo_url():
    # studentPhotoUrl is a real field the full-replace endpoint would blank.
    responses.post(
        f"{API_BASE}/getStudentsServlet",
        json={
            "students": [
                {
                    "studentId": 7,
                    "firstName": "Ada",
                    "lastName": "Lovelace",
                    "studentPhotoUrl": "https://s3/photo.jpg",
                }
            ]
        },
    )
    responses.post(f"{API_BASE}/updateStudentServlet", json={"ok": True})
    api.update_student(
        PlanbookClient("t.t.t"), student_id=7, class_id=1, last_name="Byron"
    )
    sent = dict(
        urllib.parse.parse_qsl(
            [
                c
                for c in responses.calls
                if c.request.url.endswith("/updateStudentServlet")
            ][-1].request.body
        )
    )
    assert sent["studentPhotoUrl"] == "https://s3/photo.jpg"


@responses.activate
def test_find_student_raises_on_shape_drift_not_not_found():
    responses.post(f"{API_BASE}/getStudentsServlet", json={"unexpected": 1})
    with pytest.raises(SchemaDrift):
        api.find_student(PlanbookClient("t.t.t"), student_id=7, class_id=1)


@responses.activate
def test_create_student_raises_when_nothing_was_created():
    responses.post(f"{API_BASE}/services/planbook/student/getAllFromSchool", json={})
    responses.post(f"{API_BASE}/addStudentServlet", json={"ok": True})
    with pytest.raises(ApiError):
        api.create_student(
            PlanbookClient("t.t.t"), first_name="Ada", last_name="Lovelace"
        )


@responses.activate
def test_create_unit_raises_when_nothing_was_created():
    responses.post(f"{API_BASE}/getUnits", json={"units": []})
    responses.post(f"{API_BASE}/updateUnit", json={"ok": True})
    with pytest.raises(ApiError):
        api.create_unit(PlanbookClient("t.t.t"), class_id=1, number="U1", title="Intro")


@responses.activate
def test_update_todo_raises_on_a_missing_id_instead_of_blanking():
    responses.post(f"{API_BASE}/getToDos", json={"toDos": []})
    with pytest.raises(ApiError):
        api.update_todo(PlanbookClient("t.t.t"), todo_id=999, text="x")


@responses.activate
def test_update_unit_raises_on_a_missing_id_instead_of_blanking():
    # Same guard as update_todo: an unknown id must not write blank fields.
    responses.post(f"{API_BASE}/getUnits", json={"units": []})
    with pytest.raises(ApiError):
        api.update_unit(PlanbookClient("t.t.t"), unit_id=999, class_id=1, title="X")


@responses.activate
def test_find_lesson_matches_an_unpadded_date_against_the_server_form():
    # A bulk item's "9/3/2026" must find the lesson saved on "09/03/2026",
    # not miss it and overwrite the record blank.
    responses.post(
        f"{API_BASE}/getLessonsEvents",
        json={
            "days": [
                {
                    "date": "09/03/2026",
                    "objects": [{"classId": 1, "lessonId": 9, "lessonTitle": "Keep"}],
                }
            ]
        },
    )
    found = api.find_lesson(PlanbookClient("t.t.t"), class_id=1, date="9/3/2026")
    assert found is not None
    assert found["lessonTitle"] == "Keep"


def test_parse_date_rejects_a_non_string_instead_of_crashing():
    # A bulk item with a null date must be a usage error, not an AttributeError
    # escaping main() as a traceback.
    for bad in (None, 123, ["x"]):
        with pytest.raises(UsageError):
            api.parse_date(bad)  # type: ignore[arg-type]
