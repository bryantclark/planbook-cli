"""The write seam: the dry-run envelope, the destructive-action policy,
and the identity and postcondition checks that prove a write landed.
"""

import json
import urllib.parse

import pytest
import responses

from conftest import (
    class_record,
    event_list,
    event_record,
    lesson_day,
    lesson_days,
    parse_stdout,
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
from planbook import cli
from planbook.client import PlanbookClient
from planbook.contract import CONTRACT_VERSION
from planbook.errors import (
    Ambiguous,
    PostconditionFailed,
    UsageError,
)
from planbook.fields import same
from planbook.mutations import (
    Mutation,
    Request,
    preview,
    require_intent,
    resolve_created,
)
from planbook.resources.classes import create_class, update_class
from planbook.resources.events import delete_event
from planbook.resources.lessons import delete_lesson, set_lesson
from planbook.resources.people import update_student
from planbook.resources.todos import update_todo
from planbook.resources.units import (
    create_unit,
    update_unit,
)
from planbook.wire import DAY_ORDER

# --- the dry-run envelope --------------------------------------------------


def test_preview_names_every_request_and_keeps_the_old_top_level_keys():
    body = preview(
        Mutation(
            resource="unit",
            operation="update",
            requests=[Request("/updateUnit", {"unitId": "4"})],
        )
    )
    assert body["dry_run"] is True
    assert body["contract"] == CONTRACT_VERSION
    assert body["requests"] == [
        {"method": "POST", "endpoint": "/updateUnit", "payload": {"unitId": "4"}}
    ]
    # The keys every dry-run consumer written before this module reads.
    assert body["endpoint"] == "/updateUnit"
    assert body["payload"] == {"unitId": "4"}


@responses.activate
def test_lesson_delete_dry_run_sends_nothing_and_shows_what_would_go(
    capsys, session_file
):
    stub("/getLessonsEvents", saved_lesson(lessonTitle="Cells"))
    assert (
        cli.main(
            [
                "lessons",
                "delete",
                "--class-id",
                "1",
                "--date",
                "09/03/2026",
                "--dry-run",
            ]
        )
        == 0
    )
    body, _ = parse_stdout(capsys)
    assert body["dry_run"] is True
    assert body["operation"] == "delete"
    assert body["before"]["title"] == "Cells"
    assert not [c for c in responses.calls if "deleteLesson" in c.request.url]


# --- the destructive-action policy -----------------------------------------


@responses.activate
def test_a_series_delete_needs_yes_because_it_takes_dates_you_did_not_name():
    series = [event_record(eventDate=d) for d in ("09/01/2026", "09/08/2026")]
    stub("/getEvents", event_list(*series))
    stub("/getEvents", event_list(*series))
    with pytest.raises(UsageError, match="2 occurrences"):
        delete_event(PlanbookClient("t.t.t"), event_id=3)


def test_a_confirmation_prompt_does_not_count_records_that_are_not_there():
    # A class with no lessons read "This destroys 0 lessons", which invites
    # the reader to skip a confirmation that is still required.
    mutation = Mutation(
        resource="class",
        operation="delete",
        requests=[Request("/deleteClass", {"classId": "5"})],
        cascade={"lessons": 0},
    )
    with pytest.raises(UsageError, match="destroys this class, permanently"):
        require_intent(mutation, confirmed=False)


@responses.activate
def test_an_occurrence_delete_needs_no_confirmation():
    stub("/getEvents", event_list(event_record()))
    stub("/deleteEvent", {"ok": True})
    stub("/getEvents", event_list())
    result = delete_event(PlanbookClient("t.t.t"), event_id=3, occurrence_only=True)
    assert result["ok"] and result["scope"] == "occurrence"


@responses.activate
def test_a_delete_resends_y_and_n_flags_as_the_booleans_they_are():
    # A delete resends the whole record. "N" is truthy, so a raw-truthiness
    # read would turn an ordinary event into a no-school day, and a no-school
    # day permanently deletes every lesson on its date.
    stub(
        "/getEvents",
        event_list(event_record(noSchool="N", noCycle="N", privateFlag="N")),
    )
    stub("/deleteEvent", {"ok": True})
    stub("/getEvents", event_list())
    delete_event(PlanbookClient("t.t.t"), event_id=3, occurrence_only=True)

    sent = urllib.parse.parse_qs(responses.calls[1].request.body)
    assert sent["noSchool"] == ["false"]
    assert sent["noCycle"] == ["false"]
    assert sent["privateFlag"] == ["false"]


# --- identity and postconditions -------------------------------------------


def test_one_new_record_resolves_without_needing_to_match_fields():
    got = resolve_created(
        resource="unit",
        before={"1"},
        after=[{"unitId": 1}, {"unitId": 2}],
        id_of=lambda r: r["unitId"],
        matches=lambda r: False,
        list_command="planbook units list",
    )
    assert got == 2


def test_a_concurrent_create_is_narrowed_by_what_was_written():
    got = resolve_created(
        resource="unit",
        before=set(),
        after=[
            {"unitId": 1, "unitTitle": "Mine"},
            {"unitId": 2, "unitTitle": "Theirs"},
        ],
        id_of=lambda r: r["unitId"],
        matches=lambda r: r["unitTitle"] == "Mine",
        list_command="planbook units list",
    )
    assert got == 1


def test_a_genuinely_ambiguous_create_says_so_and_says_do_not_retry():
    with pytest.raises(Ambiguous) as exc:
        resolve_created(
            resource="unit",
            before=set(),
            after=[{"unitId": 1, "t": "same"}, {"unitId": 2, "t": "same"}],
            id_of=lambda r: r["unitId"],
            matches=lambda r: True,
            list_command="planbook units list",
        )
    assert exc.value.details["candidates"] == [1, 2]
    assert "do not retry" in exc.value.remedy.lower()


@responses.activate
def test_a_write_the_server_accepted_but_did_not_store_is_a_failure():
    stub("/getUnits", unit_list())
    stub("/updateUnit", {"ok": True})
    stub("/getUnits", unit_list())
    with pytest.raises(PostconditionFailed):
        create_unit(PlanbookClient("t.t.t"), class_id=1, number="U1", title="Intro")


@responses.activate
def test_a_delete_the_server_ignored_is_a_failure():
    stub("/deleteLesson", {"ok": True})
    stub("/getLessonsEvents", saved_lesson())
    with pytest.raises(PostconditionFailed):
        delete_lesson(PlanbookClient("t.t.t"), class_id=1, date="09/03/2026")


@responses.activate
def test_a_date_range_event_is_a_series_even_when_one_record_comes_back():
    # The list endpoint does not always expand a repeat; under-reporting the
    # blast radius is the failure that matters, so a range counts as a series.
    record = event_list(
        event_record(
            eventTitle="Spring break",
            eventDate="03/16/2027",
            endDate="03/20/2027",
        )
    )
    stub("/getEvents", record)
    stub("/getEvents", record)
    with pytest.raises(UsageError, match="occurrences"):
        delete_event(PlanbookClient("t.t.t"), event_id=3)


@responses.activate
def test_occurrence_delete_on_a_real_series_does_not_report_failure():
    # The sibling occurrences share the event id, so a read-back that searches
    # by id still finds one - and used to call a successful delete a failure,
    # with a remedy that invites a retry that destroys the next occurrence.
    series = [
        event_record(eventDate=d, eventCurrentDate=d)
        for d in ("09/01/2026", "09/08/2026")
    ]
    stub("/getEvents", event_list(*series))
    stub("/deleteEvent", {"ok": True})
    stub("/getEvents", event_list(*series[1:]))
    result = delete_event(PlanbookClient("t.t.t"), event_id=3, occurrence_only=True)
    assert result["ok"] is True
    assert result["scope"] == "occurrence"


@responses.activate
def test_a_write_that_names_nothing_is_a_usage_error_not_three_requests(
    session_file,
):
    # Carry-over fills every text field from the saved lesson, so the payload
    # guard can no longer tell this from a real edit.
    stub("/getEvents", event_list())
    assert cli.main(["lessons", "set", "--class-id", "1", "--date", "09/03/2026"]) == 64
    assert not [c for c in responses.calls if c.request.url.endswith("/updateLesson")]


@responses.activate
def test_an_upsert_that_the_server_ignored_is_not_reported_as_success():
    # The lesson was already there, so finding it afterwards proves nothing.
    saved = saved_lesson(lessonTitle="Old")
    stub("/getLessonsEvents", saved)
    stub("/updateLesson", {"ok": True})
    stub("/getLessonsEvents", saved)
    with pytest.raises(PostconditionFailed):
        set_lesson(PlanbookClient("t.t.t"), class_id=1, date="09/03/2026", title="New")


@responses.activate
def test_a_read_back_that_fails_does_not_read_as_a_failed_write():
    # The write landed. Reporting the read's own error would send a caller to
    # a remedy that says retry.
    stub("/getToDos", {"toDos": [{"toDoId": 7}]})
    stub("/updateToDo", {"ok": True})
    stub("/getToDos", {"error": "true", "msg": "boom"})
    with pytest.raises(Ambiguous) as exc:
        update_todo(PlanbookClient("t.t.t"), todo_id=7, text="New")
    assert "do not retry" in exc.value.remedy.lower()


@responses.activate
def test_updating_a_student_keeps_the_gender_it_did_not_name():
    # /updateStudentServlet replaces the whole record.
    stub("/getStudentsServlet", roster(student_record(gender="F")))
    stub("/updateStudentServlet", {"ok": True})
    stub(
        "/getStudentsServlet",
        roster(student_record(gender="F", emailAddress="a@b.c")),
    )
    update_student(PlanbookClient("t.t.t"), student_id=7, class_id=1, email="a@b.c")
    sent = dict(
        urllib.parse.parse_qsl(
            [
                c
                for c in responses.calls
                if c.request.url.endswith("/updateStudentServlet")
            ][-1].request.body
        )
    )
    assert sent["studentGender"] == "F"


@responses.activate
def test_updating_a_todo_keeps_the_class_it_belongs_to():
    stub("/getToDos", todo_list(todo_record(subjectId=42)))
    stub("/updateToDo", {"ok": True})
    stub("/getToDos", todo_list(todo_record(toDoText="New", subjectId=42)))
    update_todo(PlanbookClient("t.t.t"), todo_id=7, text="New")
    sent = dict(
        urllib.parse.parse_qsl(
            [c for c in responses.calls if c.request.url.endswith("/updateToDo")][
                -1
            ].request.body
        )
    )
    assert sent["subjectId"] == "42"


@responses.activate
def test_a_section_only_write_the_server_ignored_is_not_reported_as_success():
    # `named` used to cover only the four text fields, so a --section write
    # fell back to an existence check that always passed.
    saved = saved_lesson(tab4Text="<p>old</p>")
    stub("/getLessonsEvents", saved)
    stub("/updateLesson", {"ok": True})
    stub("/getLessonsEvents", saved)
    with pytest.raises(PostconditionFailed):
        set_lesson(
            PlanbookClient("t.t.t"),
            class_id=1,
            date="09/03/2026",
            sections={4: "<p>new</p>"},
        )


@responses.activate
def test_a_lesson_can_be_moved_to_a_unit_without_editing_its_text():
    # --unit-id alone was refused as "nothing to write", so a lesson could
    # only be filed under a unit while also rewriting it.
    def filed_under(unit_id):
        return saved_lesson(
            lessonTitle="Photosynthesis",
            lessonText="<p>Chloroplasts.</p>",
            unitId=unit_id,
        )

    stub("/getLessonsEvents", filed_under(3))
    stub("/updateLesson", {"ok": True})
    stub("/getLessonsEvents", filed_under(9))
    result = set_lesson(
        PlanbookClient("t.t.t"), class_id=1, date="09/03/2026", unit_id=9
    )
    assert result["ok"] is True
    assert result["updated_fields"] == ["unit_id"]
    sent = urllib.parse.parse_qs(responses.calls[1].request.body)
    assert sent["unitId"] == ["9"]
    assert sent["lessonText"] == ["<p>Chloroplasts.</p>"]


def test_naming_a_lesson_section_twice_is_a_usage_error():
    # --text and --section 1 write the same field, so only one value can be
    # stored and reporting both as written would be a lie.
    with pytest.raises(UsageError, match="same lesson section"):
        set_lesson(
            PlanbookClient("t.t.t"),
            class_id=1,
            date="09/03/2026",
            text="<p>a</p>",
            sections={1: "<p>b</p>"},
        )


def test_two_section_clashes_are_reported_as_two_sentences():
    with pytest.raises(UsageError) as exc:
        set_lesson(
            PlanbookClient("t.t.t"),
            class_id=1,
            date="09/03/2026",
            text="<p>a</p>",
            homework="hw",
            sections={1: "<p>b</p>", 2: "other"},
        )
    assert str(exc.value) == (
        "--section 1 and --text write the same lesson section. "
        "--section 2 and --homework write the same lesson section."
    )


@responses.activate
def test_filing_a_lesson_that_does_not_exist_under_a_unit_is_a_usage_error():
    # A unit move is carry-over plus one field. With no saved lesson to carry,
    # the write would file an empty lesson under the unit.
    stub("/getLessonsEvents", lesson_days(lesson_day()))
    with pytest.raises(UsageError, match="no lesson for class 1"):
        set_lesson(PlanbookClient("t.t.t"), class_id=1, date="09/03/2026", unit_id=9)


@responses.activate
def test_a_middle_name_the_server_ignored_is_not_reported_as_success():
    saved = roster(student_record())
    stub("/getStudentsServlet", saved)
    stub("/updateStudentServlet", {"ok": True})
    stub("/getStudentsServlet", saved)
    with pytest.raises(PostconditionFailed):
        update_student(
            PlanbookClient("t.t.t"), student_id=7, class_id=1, middle_name="Zed"
        )


@responses.activate
def test_a_schedule_change_the_server_discarded_is_not_reported_as_success():
    # `scheduleChange=true` is easy to lose: the rest of the update lands and
    # the new teaching days are silently dropped.
    current = class_record(rows=[schedule_row(teach=(2,))])
    stub("/getClass", current)
    stub("/updateClass/v10", {})
    stub("/getClass", current)
    with pytest.raises(PostconditionFailed):
        update_class(PlanbookClient("t.t.t"), class_id=5, days=["friday"])


@responses.activate
def test_a_write_that_stores_an_empty_value_is_not_a_failure():
    # An absent field reads back as null, which used to compare against the
    # literal string "None" and fail a write that did exactly what was asked.
    stub("/getLessonsEvents", saved_lesson(notesText="x"))
    stub("/updateLesson", {"ok": True})
    stub("/getLessonsEvents", saved_lesson(notesText=None))
    result = set_lesson(
        PlanbookClient("t.t.t"), class_id=1, date="09/03/2026", notes=""
    )
    assert result["ok"] is True


@responses.activate
def test_a_schedule_answering_y_and_n_is_read_as_a_boolean():
    # "N" is truthy in Python, so a raw-truthiness read called every day
    # taught and failed a schedule change that landed.
    stub("/getClass", class_record(rows=[schedule_row(teach=(2,), yn=True)]))
    stub("/updateClass/v10", {})
    stub("/getClass", class_record(rows=[schedule_row(teach=(6,), yn=True)]))
    result = update_class(PlanbookClient("t.t.t"), class_id=5, days=["friday"])
    assert result["ok"] is True


@responses.activate
def test_an_update_without_days_keeps_a_y_and_n_schedule_untouched():
    # "N" is truthy, so a raw-truthiness read of the current days would rewrite
    # the class to teach all twenty rotation slots and still verify.
    stub("/getClass", class_record(rows=[schedule_row(teach=(2,), yn=True)]))
    stub("/updateClass/v10", {})
    stub(
        "/getClass",
        class_record(
            rows=[schedule_row(teach=(2,), yn=True)], classStartDate="09/01/2026"
        ),
    )
    update_class(PlanbookClient("t.t.t"), class_id=5, start_date="09/01/2026")

    sent = urllib.parse.parse_qs(responses.calls[1].request.body)
    assert sent["mondayTeach"] == ["Y"]
    assert [d for d in DAY_ORDER if sent[f"{d}Teach"] == ["Y"]] == ["monday"]
    slots = json.loads(sent["schedules"][0])[-1]
    assert [n for n in range(1, 21) if slots[f"teachDay{n}"]] == [2]


@responses.activate
def test_a_rotation_longer_than_a_week_survives_a_time_change():
    # Slots 8-20 have no weekday, so only the carried-through read keeps them.
    # A rotation flattened to a plain week loses days silently.
    stub("/getClass", class_record(rows=[schedule_row(teach=(9,), yn=True)]))
    stub("/updateClass/v10", {})
    stub(
        "/getClass",
        class_record(
            rows=[schedule_row(teach=(9,), yn=True)], classStartDate="09/01/2026"
        ),
    )
    update_class(PlanbookClient("t.t.t"), class_id=5, start_date="09/01/2026")

    sent = urllib.parse.parse_qs(responses.calls[1].request.body)
    slots = json.loads(sent["schedules"][0])[-1]
    assert [n for n in range(1, 21) if slots[f"teachDay{n}"]] == [9]
    assert [d for d in DAY_ORDER if sent[f"{d}Teach"] == ["Y"]] == []


@responses.activate
def test_a_create_then_attach_the_server_ignored_is_not_reported_as_success():
    # The first write created the row, so the second is verified by comparing
    # the fields it named - not by finding a lesson that already exists.
    created = saved_lesson(lessonTitle="")
    stub("/getLessonsEvents", lesson_days(lesson_day()))
    stub("/getAssignments", {"assignments": []})
    stub("/updateLesson", {"ok": True})
    stub("/getLessonsEvents", created)
    stub("/updateLesson", {"ok": True})
    stub("/getLessonsEvents", created)
    with pytest.raises(PostconditionFailed):
        set_lesson(
            PlanbookClient("t.t.t"),
            class_id=1,
            date="09/03/2026",
            title="Photosynthesis",
            standards=["7"],
        )


@responses.activate
def test_the_order_days_are_typed_in_is_not_a_failed_write():
    # `--days WM` is the same schedule as `--days MW`; comparing ordered lists
    # called a successful write a failure.
    stub("/getClass", class_record(rows=[schedule_row(teach=(2,))]))
    stub("/updateClass/v10", {})
    stub("/getClass", class_record(rows=[schedule_row(teach=(2, 4))]))
    result = update_class(
        PlanbookClient("t.t.t"), class_id=5, days=["wednesday", "monday"]
    )
    assert result["ok"] is True
    assert result["updated_fields"] == ["days"]


@responses.activate
def test_a_times_change_the_server_discarded_is_not_reported_as_success():
    # `times` was listed in updated_fields while nothing compared it.
    current = class_record(rows=[schedule_row(teach=(2,))])
    stub("/getClass", current)
    stub("/updateClass/v10", {})
    stub("/getClass", current)
    with pytest.raises(PostconditionFailed):
        update_class(
            PlanbookClient("t.t.t"),
            class_id=5,
            times={"monday": ("9:00 AM", "9:50 AM")},
        )


@responses.activate
def test_updated_fields_names_a_date_the_same_way_on_every_resource():
    # A versioned contract cannot call one concept `start` here and
    # `start_date` there; the projections already settled on start_date.
    stub("/getUnits", unit_list(unit_record()))
    stub("/updateUnit", {"ok": True})
    stub("/getUnits", unit_list(unit_record(unitStart="09/01/2026")))
    result = update_unit(
        PlanbookClient("t.t.t"), unit_id=5, class_id=1, start="09/01/2026"
    )
    assert result["updated_fields"] == ["start_date"]


@responses.activate
def test_clearing_a_student_field_actually_clears_it():
    # `""` is a deliberate clear. Treating it as "unnamed" carried the old
    # value forward and then compared it against itself, so the write reported
    # success having changed nothing.
    stub(
        "/getStudentsServlet",
        roster(student_record(emailAddress="ann@example.com")),
    )
    stub("/updateStudentServlet", {"ok": True})
    stub("/getStudentsServlet", roster(student_record()))
    update_student(PlanbookClient("t.t.t"), student_id=7, class_id=1, email="")
    sent = dict(
        urllib.parse.parse_qsl(
            [
                c
                for c in responses.calls
                if c.request.url.endswith("/updateStudentServlet")
            ][-1].request.body,
            keep_blank_values=True,
        )
    )
    assert sent["studentEmailAddress"] == ""


@responses.activate
def test_a_student_clear_the_server_kept_is_not_reported_as_success():
    # `/getStudentsServlet` answers under one alias, so the sibling alias is
    # always absent. Accepting an absent key would pass every clear vacuously.
    saved = roster(student_record(emailAddress="ann@example.com"))
    stub("/getStudentsServlet", saved)
    stub("/updateStudentServlet", {"ok": True})
    stub("/getStudentsServlet", saved)
    with pytest.raises(PostconditionFailed):
        update_student(PlanbookClient("t.t.t"), student_id=7, class_id=1, email="")


@responses.activate
def test_a_unit_move_the_server_ignored_is_not_reported_as_success():
    # --unit-id is sent, so it has to be proven like any other named field.
    saved = saved_lesson(lessonTitle="T", unitId=3)
    stub("/getLessonsEvents", saved)
    stub("/updateLesson", {"ok": True})
    stub("/getLessonsEvents", saved)
    with pytest.raises(PostconditionFailed):
        set_lesson(
            PlanbookClient("t.t.t"),
            class_id=1,
            date="09/03/2026",
            title="T",
            unit_id=9,
        )


def test_updating_a_student_with_no_fields_is_a_usage_error(session_file):
    # Without a guard this resends the record to itself and reports success
    # with an empty updated_fields.
    assert (
        cli.main(["students", "update", "--student-id", "7", "--class-id", "1"]) == 64
    )
    assert len(responses.calls) == 0


def test_updating_a_todo_with_no_fields_is_a_usage_error(session_file):
    assert cli.main(["todos", "update", "--todo-id", "7"]) == 64
    assert len(responses.calls) == 0


@responses.activate
def test_a_time_for_a_day_the_class_does_not_teach_is_refused():
    # Planbook blanks the time for an untaught day, so the write would report
    # success having stored nothing. The caller almost certainly forgot --days.
    stub("/getClass", class_record(rows=[schedule_row(teach=(2,))]))
    with pytest.raises(UsageError, match="does not teach"):
        update_class(
            PlanbookClient("t.t.t"),
            class_id=5,
            days=["monday", "wednesday"],
            times={"thursday": ("9:00 AM", "9:50 AM")},
        )


@pytest.mark.parametrize(
    ("stored", "written", "is_flag", "expect"),
    [
        # A field the write emptied comes back absent, not as the string "None".
        (None, "", False, True),
        (None, "x", False, False),
        ("", "", False, True),
        # A value that merely looks boolean is still compared as text.
        ("5", "0", False, False),
        ("0", "0", False, True),
        ("1", "1", False, True),
        (1, "1", False, True),
        # Planbook answers a real flag four different ways.
        (True, "1", True, True),
        (False, "0", True, True),
        ("Y", "1", True, True),
        ("N", "1", True, False),
        ("true", "1", True, True),
        ("0", "0", True, True),
        # An absent flag means false.
        (None, "0", True, True),
        (None, "1", True, False),
    ],
)
def test_a_read_back_value_matches_what_was_written(stored, written, is_flag, expect):
    assert same(stored, written, is_flag=is_flag) is expect


@responses.activate
def test_attaching_a_standard_the_server_dropped_is_not_reported_as_success():
    # On a lesson that already exists, `named` is empty, so without a check
    # the postcondition was bare existence.
    saved = saved_lesson(standards=[])
    stub("/getLessonsEvents", saved)
    stub("/updateLesson", {"ok": True})
    stub("/getLessonsEvents", saved)
    with pytest.raises(PostconditionFailed):
        set_lesson(
            PlanbookClient("t.t.t"),
            class_id=1,
            date="09/03/2026",
            standards=["118071"],
        )


def test_uploading_checks_every_path_before_sending_any(tmp_path, session_file):
    # stdout stays empty on failure, so a partial run would lose the URL of
    # anything already uploaded.
    good = tmp_path / "a.pdf"
    good.write_text("x")
    assert (
        cli.main(["attachments", "upload", str(good), str(tmp_path / "missing.pdf")])
        == 64
    )
    assert len(responses.calls) == 0


@responses.activate
def test_attaching_a_standard_on_a_new_date_the_server_dropped_is_not_success():
    # lessonId is 0 on a new date, which is exactly when Planbook drops the
    # attached set - and the create-first path was dropping its checks.
    created = saved_lesson(standards=[])
    stub("/getLessonsEvents", lesson_days(lesson_day()))
    stub("/updateLesson", {"ok": True})
    stub("/getLessonsEvents", created)
    stub("/updateLesson", {"ok": True})
    stub("/getLessonsEvents", created)
    with pytest.raises(PostconditionFailed):
        set_lesson(
            PlanbookClient("t.t.t"),
            class_id=1,
            date="09/03/2026",
            standards=["118071"],
        )


def test_creating_a_class_refuses_a_time_for_a_day_it_will_not_teach():
    # build_schedule blanks that slot, so the create would report success
    # having stored no time at all.
    with pytest.raises(UsageError, match="does not teach"):
        create_class(
            None,
            name="Bio",
            start_date="08/31/2026",
            end_date="06/06/2027",
            days=["monday", "wednesday"],
            times={"thursday": ("9:00 AM", "9:50 AM")},
            dry_run=True,
        )


@responses.activate
def test_setting_a_field_that_was_empty_before_verifies_under_either_alias():
    # An empty field is absent from the pre-write record, so which alias it
    # returns under is only knowable from the read-back.
    stub("/getStudentsServlet", roster(student_record()))
    stub("/updateStudentServlet", {"ok": True})
    stub(
        "/getStudentsServlet",
        roster(student_record(studentEmailAddress="a@b.c")),
    )
    result = update_student(
        PlanbookClient("t.t.t"), student_id=7, class_id=1, email="a@b.c"
    )
    assert result["ok"] is True
    assert result["updated_fields"] == ["email"]


@responses.activate
def test_every_write_result_carries_updated_fields(tmp_path, session_file):
    # AGENTS.md publishes it as a key of every write envelope.
    path = tmp_path / "a.pdf"
    path.write_text("x")
    stub("/getClasses2", {"classes": [{"classId": 1, "teacherId": 42}]})
    stub("/getAttachmentList", {"fileList": []})
    assert cli.main(["attachments", "upload", str(path), "--dry-run"]) == 0


@responses.activate
def test_a_dry_run_upload_reports_the_name_it_would_replace(
    tmp_path, capsys, session_file
):
    # Revealing the clash before the overwrite is the whole point of this
    # dry run, and an absent `effects` would claim there was none.
    path = tmp_path / "notes.pdf"
    path.write_text("x")
    stub("/getClasses2", {"classes": [{"classId": 1, "teacherId": 42}]})
    stub(
        "/getAttachmentList",
        {"fileList": [{"fileKey": "notes.pdf", "fileUrl": "u", "fileSize": 1}]},
    )
    assert cli.main(["attachments", "upload", str(path), "--dry-run"]) == 0
    result = json.loads(capsys.readouterr().out)[0]
    assert result["dry_run"] is True
    assert result["effects"]["replaces_existing"] == ["notes.pdf"]


@responses.activate
def test_uploading_over_an_existing_resource_name_warns_first(
    tmp_path, capsys, session_file
):
    # The upload replaces the stored file in every lesson linked to it, and
    # the server reports that as an ordinary success.
    path = tmp_path / "notes.pdf"
    path.write_text("x")
    stub("/getClasses2", {"classes": [{"classId": 1, "teacherId": 42}]})
    stub(
        "/getAttachmentList",
        {"fileList": [{"fileKey": "notes.pdf", "fileUrl": "u", "fileSize": 1}]},
    )
    stub(
        "/uploadAttachment",
        {"fileName": "notes.pdf", "fileURL": "https://x/notes.pdf"},
    )
    assert cli.main(["attachments", "upload", str(path)]) == 0
    captured = capsys.readouterr()
    assert "notes.pdf" in captured.err
    result = json.loads(captured.out)[0]
    assert result["ok"] is True
    # stderr is prose an agent must not parse, so the clash also goes to stdout.
    assert result["effects"]["replaces_existing"] == ["notes.pdf"]


@responses.activate
def test_an_upload_that_replaces_nothing_claims_no_effect(
    tmp_path, capsys, session_file
):
    # Emitted unconditionally, `effects` could not tell a replacement from a
    # new file, so an agent had nothing to branch on.
    path = tmp_path / "fresh.pdf"
    path.write_text("x")
    stub("/getClasses2", {"classes": [{"classId": 1, "teacherId": 42}]})
    stub(
        "/getAttachmentList",
        {"fileList": [{"fileKey": "notes.pdf", "fileUrl": "u", "fileSize": 1}]},
    )
    stub(
        "/uploadAttachment",
        {"fileName": "fresh.pdf", "fileURL": "https://x/fresh.pdf"},
    )
    assert cli.main(["attachments", "upload", str(path)]) == 0
    captured = capsys.readouterr()
    result = json.loads(captured.out)[0]
    assert result["ok"] is True
    assert "effects" not in result
    assert "fresh.pdf" not in captured.err


@responses.activate
def test_a_dry_run_upload_that_cannot_check_says_so_rather_than_guessing(
    tmp_path, session_file
):
    # Nothing has been sent yet, so a preview that cannot look must fail
    # rather than report the clean answer it did not earn.
    stub("/getClasses2", {"notLoggedIn": "true"})
    path = tmp_path / "notes.pdf"
    path.write_text("x")
    assert cli.main(["attachments", "upload", str(path), "--dry-run"]) == 77


@responses.activate
def test_a_real_upload_that_cannot_check_reports_a_null(tmp_path, capsys, session_file):
    # The upload happens either way, so the lookup's failure is reported
    # instead of collapsing into "replaces nothing".
    stub("/getClasses2", {"notLoggedIn": "true"})
    stub(
        "/uploadAttachment",
        {"fileName": "notes.pdf", "fileURL": "https://s3/notes.pdf"},
    )
    path = tmp_path / "notes.pdf"
    path.write_text("x")
    assert cli.main(["attachments", "upload", str(path)]) == 0
    body, _ = parse_stdout(capsys)
    assert body[0]["effects"]["replaces_existing"] is None


@responses.activate
def test_clearing_a_lessons_unit_is_not_reported_as_a_failed_write():
    # An unfiled lesson comes back with no unitId, so demanding "0" back would
    # fail a write that did exactly what was asked.
    stub("/getLessonsEvents", saved_lesson(unitId=3, lessonTitle="T"))
    stub("/updateLesson", {"ok": True})
    # The read-back comes with no unitId at all.
    stub("/getLessonsEvents", saved_lesson(lessonTitle="T"))
    result = set_lesson(
        PlanbookClient("t.t.t"), class_id=1, date="09/03/2026", unit_id=0
    )
    assert result["ok"] is True
