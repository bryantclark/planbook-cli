import pytest
import requests
import responses

from planbook.client import API_BASE, PlanbookClient, intish, yn
from planbook.errors import ApiError, NotAuthenticated, SchemaDrift


def response(status, text):
    resp = requests.Response()
    resp.status_code = status
    resp._content = text.encode()
    return resp


def client():
    return PlanbookClient("cookie")


def test_check_maps_not_logged_in_to_not_authenticated():
    with pytest.raises(NotAuthenticated):
        client()._check(
            response(200, '{"notLoggedIn":"true"}'),
            "https://api.planbook.com/getClasses2",
        )


def test_check_maps_error_body_to_api_error_message():
    with pytest.raises(ApiError, match="bad field"):
        client()._check(
            response(200, '{"error":"true","msg":"bad field"}'),
            "https://api.planbook.com/updateLesson",
        )


def test_check_maps_non_json_to_schema_drift():
    with pytest.raises(SchemaDrift, match="non-JSON"):
        client()._check(
            response(200, "<html>nope</html>"), "https://api.planbook.com/getClasses2"
        )


def test_check_maps_waf_405_to_schema_drift():
    with pytest.raises(SchemaDrift, match="AWS WAF"):
        client()._check(
            response(405, "AWSWAF human verification"),
            "https://api.planbook.com/getClasses2",
        )


def test_check_returns_normal_dict_unchanged():
    body = client()._check(
        response(200, '{"classes":[]}'), "https://api.planbook.com/getClasses2"
    )
    assert body == {"classes": []}


def test_require_names_missing_keys():
    with pytest.raises(SchemaDrift) as exc:
        client().require(
            {"classes": []},
            "classes",
            "currentYearId",
            "lessonBanks",
            where="getClasses2",
        )
    message = str(exc.value)
    assert "currentYearId" in message
    assert "lessonBanks" in message


def test_wire_value_helpers():
    assert yn(True) == "Y"
    assert yn(False) == "N"
    assert intish(None) == "0"
    assert intish("") == "0"
    assert intish(5) == "5"


def test_user_agent_header_is_set():
    ua = client().http.headers["User-Agent"]
    assert "planbook-cli" in ua


@responses.activate
def test_get_sends_a_query_not_a_body():
    # Part of the API is GET-only and answers a POST with 405.
    responses.get(f"{API_BASE}/services/planbook/attendance/get", json={})
    PlanbookClient("t.t.t").get(
        "/services/planbook/attendance/get", {"classId": "1", "date": "09/08/2026"}
    )
    assert responses.calls[0].request.method == "GET"
    assert "classId=1" in responses.calls[0].request.url


@responses.activate
def test_405_error_says_the_endpoint_is_get_only():
    responses.post(
        f"{API_BASE}/services/planbook/attendance/get",
        json={"error": "true", "message": "HTTP 405 Method Not Allowed"},
    )
    with pytest.raises(ApiError, match="GET-only"):
        PlanbookClient("t.t.t").post("/services/planbook/attendance/get")


@responses.activate
def test_post_json_sends_a_json_body():
    responses.post(f"{API_BASE}/x", json={})
    PlanbookClient("t.t.t").post_json("/x", {"a": 1})
    assert responses.calls[0].request.headers["Content-Type"] == "application/json"
