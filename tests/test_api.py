import pytest
import responses

from planbook import api
from planbook.client import API_BASE, PlanbookClient
from planbook.errors import SchemaDrift, UsageError


def class_wire_record():
    raw = {"cId": 123, "cN": "Biology", "cSd": "08/31/2026", "cEd": "06/06/2027"}
    for prefix in ["m", "t", "w", "r", "f", "s", "u"]:
        raw[f"{prefix}T"] = f"{prefix}-teach"
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
    assert result["schedule"]["thursday"] == {"teaches": "r-teach", "start": "r-start", "end": "r-end"}
    assert result["schedule"]["sunday"] == {"teaches": "u-teach", "start": "u-start", "end": "u-end"}


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
