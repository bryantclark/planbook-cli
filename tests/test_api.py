import json
import urllib.parse

import pytest
import responses

from conftest import (
    class_record,
    class_wire_record,
    event_list,
    event_record,
    lesson_day,
    lesson_days,
    lesson_record,
    roster,
    saved_lesson,
    schedule_row,
    stub,
    student_record,
    todo_list,
    todo_record,
    unit_list,
    unit_record,
)
from planbook.client import PlanbookClient
from planbook.errors import ApiError, SchemaDrift, UsageError
from planbook.resources.classes import (
    class_payload,
    list_classes,
    normalize_class,
    raw_classes,
    update_class,
)
from planbook.resources.events import create_event, event_payload
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
from planbook.resources.people import (
    create_student,
    find_student,
    list_students,
    student_payload,
    update_student,
)
from planbook.resources.todos import update_todo
from planbook.resources.units import create_unit, delete_unit, unit_payload, update_unit
from planbook.wire import (
    build_schedule,
    parse_date,
    parse_day_times,
    parse_days,
    parse_time,
)


def test_parse_days_weekdays_and_special_letters():
    assert parse_days("MTWRF") == [
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
    ]
    assert parse_days("RU") == ["thursday", "sunday"]


def test_parse_days_rejects_unknown_letter():
    with pytest.raises(UsageError):
        parse_days("X")


def test_normalize_class_maps_fields_and_all_day_schedule():
    result = normalize_class(class_wire_record())
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
    result = normalize_class(class_wire_record(teach_days=("m", "w", "f")))
    teaching = [d for d, v in result["schedule"].items() if v["teaches"]]
    assert teaching == ["monday", "wednesday", "friday"]


def test_build_schedule_indexes_from_sunday():
    # teachDay1 is Sunday, not Monday; an off-by-one silently shifts every day.
    slot = json.loads(build_schedule(["monday", "wednesday", "friday"], "08/31/2026"))[
        0
    ]
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
    stub(
        "/getClass",
        class_record(
            rows=[schedule_row(teach=(2, 4, 6), start_times={2: "9:00 AM"})],
            classId=5,
            classEndDate="06/06/2027",
            color="#FF00FF",
            classDesc="keep me",
            titleColor="#111111",
            titleSize="14",
            titleFont="Georgia",
            lessonLayoutId=77,
            noStudents=True,
            useSchoolStart="N",
            useSchoolEnd="N",
            classLabelBold=True,
            classLabelItalic=False,
            classLabelUnderline=False,
            source="",
            sourceId="0",
            collaborateType=0,
            collaborateSubjectId=0,
            collaborateKey="",
            mondayTeach="Y",
            tuesdayTeach="N",
            wednesdayTeach="Y",
            thursdayTeach="N",
            fridayTeach="Y",
            saturdayTeach="N",
            sundayTeach="N",
            mondayStartTime="09:00",
            mondayEndTime="10:00",
        ),
    )
    stub("/updateClass/v10", {})
    stub("/getClass", {"className": "Bio 2"})

    update_class(PlanbookClient("t.t.t"), class_id=5, name="Bio 2")

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
    stub(
        "/getClass",
        class_record(
            rows=[schedule_row(teach=(2, 4, 6))],
            classId=5,
            classEndDate="06/06/2027",
            mondayTeach="Y",
            wednesdayTeach="Y",
            fridayTeach="Y",
            tuesdayTeach="N",
            thursdayTeach="N",
            saturdayTeach="N",
            sundayTeach="N",
        ),
    )
    stub("/updateClass/v10", {})
    # The read-back that proves the new schedule took: Tue/Thu, slots 3 and 5.
    stub("/getClass", class_record(rows=[schedule_row(teach=(3, 5))]))
    update_class(PlanbookClient("t.t.t"), class_id=5, days=["tuesday", "thursday"])
    sent = dict(urllib.parse.parse_qsl(responses.calls[1].request.body))
    assert sent["mondayTeach"] == "N" and sent["tuesdayTeach"] == "Y"


def test_class_payload_uses_yn_not_true_false():
    # true/false is accepted and silently produces a class teaching no days.
    payload = class_payload(
        name="X", start_date="08/31/2026", end_date="06/06/2027", days=["monday"]
    )
    assert payload["mondayTeach"] == "Y"
    assert payload["tuesdayTeach"] == "N"
    assert payload["verifyShift"] == "false"


def test_event_payload_commits_rather_than_only_validating():
    # verifyShift="true" answers exactly like success and writes nothing.
    payload = event_payload(
        {"eventTitle": "X", "eventDate": "09/15/2026", "endDate": "09/15/2026"}
    )
    assert payload["verifyShift"] == "false"
    assert payload["eventCurrentDate"] == ""
    assert payload["shiftLessons"] == "N"


def test_unit_payload_sends_class_id_as_subject_id():
    payload = unit_payload(action="A", class_id=99, number="U1", title="T")
    assert payload["subjectId"] == "99"
    assert payload["action"] == "A"


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


@responses.activate
def test_list_classes_normalizes_and_raw_returns_untouched_body():
    body = {
        "currentYearId": 99,
        "classes": [class_wire_record()],
        "lessonBanks": [{"id": 1}],
        "districtLessonBanks": [{"id": 2}],
    }
    stub("/getClasses2", body)
    stub("/getClasses2", body)
    client = PlanbookClient("t.t.t")

    mapped = list_classes(client)
    raw = raw_classes(client)

    assert mapped["current_year_id"] == 99
    assert mapped["classes"][0]["id"] == 123
    assert mapped["lesson_banks"] == [{"id": 1}]
    assert mapped["district_lesson_banks"] == [{"id": 2}]
    assert raw is not body
    assert raw == body


@responses.activate
def test_list_classes_raises_schema_drift_without_classes_key():
    stub("/getClasses2", {"currentYearId": 99})
    with pytest.raises(SchemaDrift):
        list_classes(PlanbookClient("t.t.t"))


def test_parse_time_accepts_24h_and_12h():
    # Planbook stores only 12-hour times; a 24-hour string is accepted on the
    # wire and stored as empty, silently losing the time.
    assert parse_time("14:30") == "2:30 PM"
    assert parse_time("09:00") == "9:00 AM"
    assert parse_time("9:00am") == "9:00 AM"
    assert parse_time("9:00 AM") == "9:00 AM"
    assert parse_time("") == ""
    assert parse_time(None) == ""


def test_parse_time_handles_noon_and_midnight():
    assert parse_time("12:00") == "12:00 PM"
    assert parse_time("00:15") == "12:15 AM"
    assert parse_time("12:00 AM") == "12:00 AM"


def test_parse_time_rejects_nonsense():
    for bad in ("9:5", "25:00", "10:99", "lunchtime"):
        with pytest.raises(UsageError):
            parse_time(bad)


def test_parse_day_times_whole_week_and_per_day():
    assert parse_day_times(["9:00-9:50"], ["monday", "friday"]) == {
        "monday": ("9:00 AM", "9:50 AM"),
        "friday": ("9:00 AM", "9:50 AM"),
    }
    assert parse_day_times(["M=8:00-8:45", "W=13:00-13:50"], []) == {
        "monday": ("8:00 AM", "8:45 AM"),
        "wednesday": ("1:00 PM", "1:50 PM"),
    }


def test_lesson_payload_never_sets_a_custom_time():
    # The server ignores customStart/customEnd on /updateLesson - a lesson
    # always keeps its class period's times - so the CLI does not offer them.
    payload = lesson_payload(class_id=1, date="09/01/2026", title="T")[0]
    assert payload["customStart"] == ""
    assert payload["customEnd"] == ""
    assert "CUSTOMSTART" not in payload["updatedFields"]


def test_build_schedule_carries_per_day_times():
    slot = json.loads(
        build_schedule(["monday"], "08/31/2026", {"monday": ("9:00 AM", "9:50 AM")})
    )[0]
    assert slot["startDay2"] == "9:00 AM"  # teachDay2 is Monday
    assert slot["endDay2"] == "9:50 AM"
    assert slot["startDay3"] == ""  # Tuesday, not taught


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


@responses.activate
def test_update_class_preserves_rotation_slots_beyond_the_week():
    # A 10-day rotation must survive a rename. Rebuilding from a blank
    # template would flatten it into an ordinary week, silently.
    stub(
        "/getClass",
        class_record(
            rows=[
                schedule_row(
                    teach=(2, 9, 10),
                    start_times={9: "1:00 PM"},
                    additionalClassDays=[{"x": 1}],
                )
            ],
            classEndDate="06/06/2027",
        ),
    )
    stub("/updateClass/v10", {})
    stub("/getClass", {"className": "Bio 2"})
    update_class(PlanbookClient("t.t.t"), class_id=5, name="Bio 2")
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
    stub("/getClass", {"className": "Bio"})
    with pytest.raises(SchemaDrift):
        update_class(PlanbookClient("t.t.t"), class_id=5, name="Bio 2")


@responses.activate
def test_update_class_keeps_earlier_schedule_rows_untouched():
    stub(
        "/getClass",
        class_record(
            rows=[
                schedule_row(teach=(2,), scheduleStart="08/31/2026"),
                schedule_row(teach=(4,), scheduleStart="01/05/2027"),
            ]
        ),
    )
    stub("/updateClass/v10", {})
    # The read-back that proves the new schedule took: Friday is slot 6.
    stub("/getClass", class_record(rows=[schedule_row(teach=(6,))]))
    update_class(PlanbookClient("t.t.t"), class_id=5, days=["friday"])
    rows = json.loads(
        dict(urllib.parse.parse_qsl(responses.calls[1].request.body))["schedules"]
    )
    assert rows[0]["teachDay2"] is True  # history untouched
    assert rows[1]["teachDay6"] is True  # newest row edited to Friday
    assert rows[1]["teachDay4"] is False


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
def test_no_school_event_allowed_with_force():
    # --force must bypass the guard AND actually send noSchool=true; the old
    # test only checked ok, so it would have passed even if force did nothing.
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
    assert result["id"] == 555


@responses.activate
def test_no_school_event_blocked_without_force_when_lessons_exist():
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


def test_student_payload_omits_id_when_creating():
    payload = student_payload(first_name="Ada", last_name="Lovelace")
    assert "studentId" not in payload
    assert payload["studentFirstName"] == "Ada"
    assert payload["userMode"] == "T"


def test_student_payload_includes_id_when_updating():
    payload = student_payload(first_name="Ada", last_name="Lovelace", student_id=7)
    assert payload["studentId"] == "7"


@responses.activate
def test_list_students_treats_a_non_id_key_as_drift():
    stub(
        "/services/planbook/student/getAllFromSchool",
        {"status": "ok", "2139917": "Lovelace, Ada"},
    )
    with pytest.raises(SchemaDrift):
        list_students(PlanbookClient("t.t.t"))


@responses.activate
def test_list_students_normalizes_both_shapes():
    # Account-wide returns {id: "Last, First"}; per-class returns records.
    stub(
        "/services/planbook/student/getAllFromSchool",
        {"2139917": "Lovelace, Ada"},
    )
    everyone = list_students(PlanbookClient("t.t.t"))
    assert everyone == [
        {"id": 2139917, "name": "Lovelace, Ada", "last_name": "Lovelace"}
    ]

    stub("/getStudentsServlet", roster(student_record(studentId=1)))
    in_class = list_students(PlanbookClient("t.t.t"), class_id=5)
    assert in_class[0]["first_name"] == "Ada"


@responses.activate
def test_list_students_rejects_a_shape_it_does_not_recognise():
    stub("/getStudentsServlet", {"nope": []})
    with pytest.raises(SchemaDrift):
        list_students(PlanbookClient("t.t.t"), class_id=5)


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


def test_parse_date_rejects_what_the_server_answers_with_a_null_pointer():
    # An impossible date used to reach Planbook, which replied with a Java NPE
    # about Schedule.getScheduleStart() - an API error, not a usage error.
    assert parse_date("09/03/2026") == "09/03/2026"
    # Zero-padded so it matches the server's format on find_lesson's exact
    # string compare; an unpadded date used to miss the saved lesson and blank
    # it on write.
    assert parse_date("9/3/2026") == "09/03/2026"
    assert parse_date("12/1/2026") == "12/01/2026"
    for bad in ("13/45/2026", "notadate", "2026-09-03", "09/31/2026", "9/3/26"):
        with pytest.raises(UsageError):
            parse_date(bad)


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
def test_update_todo_carries_over_what_the_caller_did_not_name():
    # /updateToDo replaces the whole record, so a payload built from defaults
    # silently reopened a completed to-do and reset its priority.
    stub(
        "/getToDos",
        todo_list(
            todo_record(
                startDate="09/01/2026",
                dueDate="09/05/2026",
                priority="3",
                done="1",
                repeats="weekly",
            )
        ),
    )
    stub("/updateToDo", {"ok": True})
    # The read-back that proves the new text landed.
    stub("/getToDos", todo_list(todo_record(toDoText="New")))
    update_todo(PlanbookClient("t.t.t"), todo_id=7, text="New")
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
def test_update_student_carries_over_and_needs_the_class():
    # /updateStudentServlet replaces the whole record, so a rename used to
    # blank the email, phone and parent email the student had on file.
    stub(
        "/getStudentsServlet",
        roster(
            student_record(
                lastName="Lovelace",
                emailAddress="ada@x.z",
                phoneNumber="555-0100",
                parentEmailAddress="parent@x.z",
            )
        ),
    )
    stub("/updateStudentServlet", {"ok": True})
    # The read-back that proves the rename landed.
    stub("/getStudentsServlet", roster(student_record(lastName="Byron")))
    update_student(PlanbookClient("t.t.t"), student_id=7, class_id=1, last_name="Byron")
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
    stub("/getStudentsServlet", roster())
    with pytest.raises(ApiError):
        update_student(
            PlanbookClient("t.t.t"), student_id=7, class_id=1, first_name="Ada"
        )


@responses.activate
def test_update_student_carries_over_the_photo_url():
    # studentPhotoUrl is a real field the full-replace endpoint would blank.
    stub(
        "/getStudentsServlet",
        roster(
            student_record(lastName="Lovelace", studentPhotoUrl="https://s3/photo.jpg")
        ),
    )
    stub("/updateStudentServlet", {"ok": True})
    # The read-back that proves the rename landed.
    stub("/getStudentsServlet", roster(student_record(lastName="Byron")))
    update_student(PlanbookClient("t.t.t"), student_id=7, class_id=1, last_name="Byron")
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
    stub("/getStudentsServlet", {"unexpected": 1})
    with pytest.raises(SchemaDrift):
        find_student(PlanbookClient("t.t.t"), student_id=7, class_id=1)


@responses.activate
def test_create_student_raises_when_nothing_was_created():
    stub("/services/planbook/student/getAllFromSchool", {})
    stub("/addStudentServlet", {"ok": True})
    with pytest.raises(ApiError):
        create_student(PlanbookClient("t.t.t"), first_name="Ada", last_name="Lovelace")


@responses.activate
def test_create_unit_raises_when_nothing_was_created():
    stub("/getUnits", unit_list())
    stub("/updateUnit", {"ok": True})
    with pytest.raises(ApiError):
        create_unit(PlanbookClient("t.t.t"), class_id=1, number="U1", title="Intro")


@responses.activate
def test_update_todo_raises_on_a_missing_id_instead_of_blanking():
    stub("/getToDos", todo_list())
    with pytest.raises(ApiError):
        update_todo(PlanbookClient("t.t.t"), todo_id=999, text="x")


@responses.activate
def test_update_unit_raises_on_a_missing_id_instead_of_blanking():
    # Same guard as update_todo: an unknown id must not write blank fields.
    stub("/getUnits", unit_list())
    with pytest.raises(ApiError):
        update_unit(PlanbookClient("t.t.t"), unit_id=999, class_id=1, title="X")


@responses.activate
def test_find_lesson_matches_an_unpadded_date_against_the_server_form():
    # A bulk item's "9/3/2026" must find the lesson saved on "09/03/2026",
    # not miss it and overwrite the record blank.
    stub("/getLessonsEvents", saved_lesson(lessonId=9, lessonTitle="Keep"))
    found = find_lesson(PlanbookClient("t.t.t"), class_id=1, date="9/3/2026")
    assert found is not None
    assert found["lessonTitle"] == "Keep"


def test_parse_date_rejects_a_non_string_instead_of_crashing():
    # A bulk item with a null date must be a usage error, not an AttributeError
    # escaping main() as a traceback.
    for bad in (None, 123, ["x"]):
        with pytest.raises(UsageError):
            parse_date(bad)  # type: ignore[arg-type]


@responses.activate
def test_a_json_boolean_error_is_still_an_error():
    # Planbook answers `{"error": "true"}`, but a string compare would read a
    # real JSON boolean as success and hand back a failed write.
    stub("/getClasses2", {"error": True, "msg": "nope"})
    with pytest.raises(ApiError):
        PlanbookClient("t.t.t").post("/getClasses2", {})


@responses.activate
def test_a_json_boolean_false_error_is_a_success():
    # `flag` reads truthiness, not presence: a false alarm here would fail
    # every command in the tool.
    for body in ({"error": "false"}, {"error": 0}, {"error": False}):
        stub("/getClasses2", body)
        assert PlanbookClient("t.t.t").post("/getClasses2", {}) == body


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
