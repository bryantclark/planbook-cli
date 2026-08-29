"""Students, attendance and grades.

Students are account-wide; a class sees the subset enrolled in it. Attendance
is read-only here: `/services/planbook/attendance/get` answers a GET, but no
write endpoint exists under that path, so recording attendance still needs
the web UI.
"""

from __future__ import annotations

from typing import Any

from ..client import PlanbookClient
from ..errors import SchemaDrift
from ..wire import intish


def list_students(client: PlanbookClient, *, class_id: Any = None) -> Any:
    """Students in one class, or every student on the account.

    The account-wide endpoint answers `{id: "Last, First"}`; the per-class one
    returns full records, so they are normalised to the same shape.
    """
    if class_id is None:
        body = client.post("/services/planbook/student/getAllFromSchool")
        if not isinstance(body, dict):
            raise SchemaDrift("getAllFromSchool did not return an object.")
        return [
            {"id": int(k), "name": v, "last_name": str(v).split(",")[0].strip()}
            for k, v in body.items()
        ]
    body = client.post(
        "/getStudentsServlet", {"classId": intish(class_id), "userMode": "T"}
    )
    students = body.get("students") if isinstance(body, dict) else None
    if not isinstance(students, list):
        raise SchemaDrift("getStudentsServlet returned no `students` list.")
    return [
        {
            "id": s.get("studentId") or s.get("id"),
            "first_name": s.get("firstName"),
            "last_name": s.get("lastName"),
            "code": s.get("code"),
            "email": s.get("emailAddress"),
            "gender": s.get("gender"),
        }
        for s in students
    ]


def student_payload(
    *,
    first_name: str,
    last_name: str,
    student_id: Any = 0,
    code: str = "",
    email: str = "",
    phone: str = "",
    parent_email: str = "",
    birthdate: str = "",
    middle_name: str = "",
) -> dict[str, str]:
    payload = {
        "studentCode": code,
        "studentPassword": "",
        "studentFirstName": first_name,
        "studentMiddleName": middle_name,
        "studentLastName": last_name,
        "studentEmailAddress": email,
        "studentPhoneNumber": phone,
        "parentEmailAddress": parent_email,
        "studentBirthDate": birthdate,
        "schoolDistrictId": "0",
        "userMode": "T",
        "studentPhotoUrl": "",
    }
    if student_id:
        payload["studentId"] = intish(student_id)
    return payload


def create_student(client: PlanbookClient, **fields: Any) -> dict[str, Any]:
    client.post("/addStudentServlet", student_payload(**fields))
    return {"ok": True, "name": f"{fields['first_name']} {fields['last_name']}"}


def update_student(
    client: PlanbookClient, *, student_id: Any, **fields: Any
) -> dict[str, Any]:
    client.post(
        "/updateStudentServlet", student_payload(student_id=student_id, **fields)
    )
    return {"ok": True, "student_id": intish(student_id)}


def delete_student(client: PlanbookClient, *, student_id: Any) -> dict[str, Any]:
    client.post(
        "/deleteStudentServlet", {"studentId": intish(student_id), "userMode": "T"}
    )
    return {"ok": True, "deleted_student_id": intish(student_id)}


def get_attendance(client: PlanbookClient, *, class_id: Any, date: str) -> Any:
    """Attendance for one class on one date. Read-only: this endpoint is GET,
    and no write endpoint exists under the same path."""
    return client.get(
        "/services/planbook/attendance/get",
        {"classId": intish(class_id), "date": date},
    )


def get_scores(client: PlanbookClient, *, class_id: Any) -> Any:
    """Grade periods and assignments with scores for one class."""
    return client.post(
        "/getStudentScoresServlet",
        {"classId": intish(class_id), "subjectId": intish(class_id), "userMode": "T"},
    )


def list_templates(client: PlanbookClient, *, teacher_id: Any) -> Any:
    body = client.get(
        "/services/planbook/template/get", {"teacherId": intish(teacher_id)}
    )
    if isinstance(body, dict) and set(body) == {"templates"}:
        return body["templates"]
    return body
