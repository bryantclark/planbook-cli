"""The class resource: projection, payloads and schedule-preserving updates."""

import json
import urllib.parse

import pytest
import responses

from conftest import (
    class_record,
    class_wire_record,
    schedule_row,
    stub,
)
from planbook.client import PlanbookClient
from planbook.errors import SchemaDrift
from planbook.resources.classes import (
    class_payload,
    list_classes,
    normalize_class,
    raw_classes,
    update_class,
)


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
