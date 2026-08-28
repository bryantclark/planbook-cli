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


def test_parse_days_weekdays_and_special_letters():
    assert api.parse_days("MTWRF") == ["monday", "tuesday", "wednesday", "thursday", "friday"]
    assert api.parse_days("RU") == ["thursday", "sunday"]


def test_parse_days_rejects_unknown_letter():
    with pytest.raises(UsageError):
        api.parse_days("X")


def test_normalize_class_maps_fields_and_all_day_schedule():
    result = api.normalize_class(class_wire_record())
    assert result["id"] == 123
    assert result["name"] == "Biology"
    assert set(result["schedule"]) == {
        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"
    }
    assert result["schedule"]["thursday"] == {"teaches": True, "start": "r-start", "end": "r-end"}
    assert result["schedule"]["sunday"] == {"teaches": False, "start": "u-start", "end": "u-end"}


def test_normalize_class_turns_yn_flags_into_booleans():
    # "N" is truthy in Python; passed through it would read as "teaches".
    result = api.normalize_class(class_wire_record(teach_days=("m", "w", "f")))
    teaching = [d for d, v in result["schedule"].items() if v["teaches"]]
    assert teaching == ["monday", "wednesday", "friday"]


def test_build_schedule_indexes_from_sunday():
    # teachDay1 is Sunday, not Monday; an off-by-one silently shifts every day.
    slot = json.loads(api.build_schedule(["monday", "wednesday", "friday"], "08/31/2026"))[0]
    assert slot["teachDay1"] is False   # Sunday
    assert slot["teachDay2"] is True    # Monday
    assert slot["teachDay4"] is True    # Wednesday
    assert slot["teachDay6"] is True    # Friday
    assert slot["teachDay7"] is False   # Saturday
    assert slot["scheduleStart"] == "08/31/2026"


@responses.activate
def test_update_class_preserves_fields_it_was_not_asked_to_change():
    # The endpoint replaces the whole record, so a rename must not blank the
    # description, colour, layout or per-day times.
    responses.post(f"{API_BASE}/getClass", json={
        "classId": 5, "className": "Bio", "classStartDate": "08/31/2026",
        "classEndDate": "06/06/2027", "color": "#FF00FF", "classDesc": "keep me",
        "titleColor": "#111111", "titleSize": "14", "titleFont": "Georgia",
        "lessonLayoutId": 77, "noStudents": True, "useSchoolStart": "N",
        "useSchoolEnd": "N", "classLabelBold": True, "classLabelItalic": False,
        "classLabelUnderline": False, "source": "", "sourceId": "0",
        "collaborateType": 0, "collaborateSubjectId": 0, "collaborateKey": "",
        "mondayTeach": "Y", "tuesdayTeach": "N", "wednesdayTeach": "Y",
        "thursdayTeach": "N", "fridayTeach": "Y", "saturdayTeach": "N",
        "sundayTeach": "N",
        "mondayStartTime": "09:00", "mondayEndTime": "10:00",
    })
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
    assert json.loads(sent["schedules"])[0]["startDay2"] == "09:00"
    # and the flags that make the write actually land
    assert sent["scheduleChange"] == "true"
    assert sent["verifyShift"] == "false"


@responses.activate
def test_update_class_replaces_schedule_when_days_given():
    responses.post(f"{API_BASE}/getClass", json={
        "classId": 5, "className": "Bio", "classStartDate": "08/31/2026",
        "classEndDate": "06/06/2027", "mondayTeach": "Y", "wednesdayTeach": "Y",
        "fridayTeach": "Y", "tuesdayTeach": "N", "thursdayTeach": "N",
        "saturdayTeach": "N", "sundayTeach": "N",
    })
    responses.post(f"{API_BASE}/updateClass/v10", json={})
    api.update_class(PlanbookClient("t.t.t"), class_id=5, days=["tuesday", "thursday"])
    sent = dict(urllib.parse.parse_qsl(responses.calls[1].request.body))
    assert sent["mondayTeach"] == "N" and sent["tuesdayTeach"] == "Y"


def test_class_payload_uses_yn_not_true_false():
    # true/false is accepted and silently produces a class teaching no days.
    payload = api.create_class(None, name="X", start_date="08/31/2026",
                               end_date="06/06/2027", days=["monday"],
                               dry_run=True)["payload"]
    assert payload["mondayTeach"] == "Y"
    assert payload["tuesdayTeach"] == "N"
    assert payload["verifyShift"] == "false"


def test_event_payload_commits_rather_than_only_validating():
    # verifyShift="true" answers exactly like success and writes nothing.
    payload = api.create_event(None, title="X", date="09/15/2026",
                               dry_run=True)["payload"]
    assert payload["verifyShift"] == "false"
    assert payload["eventCurrentDate"] == ""
    assert payload["shiftLessons"] == "N"


def test_unit_payload_sends_class_id_as_subject_id():
    payload = api.create_unit(None, class_id=99, number="U1", title="T",
                              dry_run=True)["payload"]
    assert payload["subjectId"] == "99"
    assert payload["action"] == "A"


def test_delete_lesson_payload():
    payload = api.delete_lesson(None, class_id=7, date="09/01/2026",
                                dry_run=True)["payload"]
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
