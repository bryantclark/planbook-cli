"""The student resource."""

import urllib.parse

import pytest
import responses

from conftest import (
    roster,
    stub,
    student_record,
)
from planbook.client import PlanbookClient
from planbook.errors import ApiError, SchemaDrift
from planbook.resources.people import (
    create_student,
    find_student,
    list_students,
    student_payload,
    update_student,
)


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
