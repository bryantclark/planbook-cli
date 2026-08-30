"""Students, attendance and grades.

Students are account-wide; a class sees the subset enrolled in it. Attendance
is read-only here: `/services/planbook/attendance/get` answers a GET, but no
write endpoint exists under that path, so recording attendance still needs
the web UI.
"""

from __future__ import annotations

from typing import Any

from ..client import PlanbookClient
from ..errors import ApiError, SchemaDrift
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
    photo_url: str = "",
    district_id: str = "0",
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
        "schoolDistrictId": district_id or "0",
        "userMode": "T",
        # A full-replace endpoint: a saved photo is lost unless carried over.
        "studentPhotoUrl": photo_url,
    }
    if student_id:
        payload["studentId"] = intish(student_id)
    return payload


def create_student(
    client: PlanbookClient | None, *, dry_run: bool = False, **fields: Any
) -> dict[str, Any]:
    if dry_run:
        return {
            "dry_run": True,
            "endpoint": "/addStudentServlet",
            "payload": student_payload(**fields),
        }

    assert client is not None  # only the dry_run branch runs without one

    # /addStudentServlet does not report the new id. Diff the account roster
    # around the write so the caller gets a student_id to update or delete.
    def roster_ids() -> set[str]:
        return {
            str(s.get("id"))
            for s in (list_students(client) or [])
            if isinstance(s, dict) and s.get("id") is not None
        }

    before = roster_ids()
    client.post("/addStudentServlet", student_payload(**fields))
    created = roster_ids() - before
    if not created:
        raise ApiError(
            "Creating the student did not take: no new student appeared. "
            "The server returns HTTP 200 even when it stores nothing."
        )
    return {
        "ok": True,
        "name": f"{fields['first_name']} {fields['last_name']}",
        "student_id": created.pop() if len(created) == 1 else None,
    }


def find_student(
    client: PlanbookClient, *, student_id: Any, class_id: Any
) -> dict[str, Any] | None:
    """The raw student record from the per-class endpoint, or None.

    There is no get-one endpoint, and the account-wide list returns names
    only, so a full record needs the class the student sits in.
    """
    body = client.post(
        "/getStudentsServlet", {"classId": intish(class_id), "userMode": "T"}
    )
    students = body.get("students") if isinstance(body, dict) else None
    if not isinstance(students, list):
        # Same shape check as list_students: a missing list is drift (exit 65),
        # not a not-found student (which would wrongly blame the caller).
        raise SchemaDrift("getStudentsServlet returned no `students` list.")
    for record in students:
        if isinstance(record, dict) and str(
            record.get("studentId") or record.get("id")
        ) == str(intish(student_id)):
            return record
    return None


def update_student(
    client: PlanbookClient,
    *,
    student_id: Any,
    class_id: Any,
    dry_run: bool = False,
    **fields: Any,
) -> dict[str, Any]:
    """Update a student, carrying over whatever the caller did not name.

    `/updateStudentServlet` replaces the whole record, so a payload built from
    defaults blanks the email, phone, parent email, code and birthdate. Reads
    the current record first, keyed by the class the student is in.
    """
    existing = find_student(client, student_id=student_id, class_id=class_id)
    if existing is None:
        raise ApiError(
            f"No student {student_id} in class {class_id}. Pass the --class-id "
            "the student is in so their other fields are not lost."
        )

    def keep(name: str, *raw_keys: str) -> str:
        value = fields.get(name)
        if value not in (None, ""):
            return str(value)
        for key in raw_keys:
            if existing.get(key) not in (None, ""):
                return str(existing[key])
        return ""

    payload = student_payload(
        student_id=student_id,
        first_name=keep("first_name", "firstName"),
        last_name=keep("last_name", "lastName"),
        code=keep("code", "code", "studentCode"),
        email=keep("email", "emailAddress", "studentEmailAddress"),
        phone=keep("phone", "phoneNumber", "studentPhoneNumber"),
        parent_email=keep("parent_email", "parentEmailAddress"),
        birthdate=keep("birthdate", "birthDate", "studentBirthDate"),
        middle_name=keep("middle_name", "middleName", "studentMiddleName"),
        photo_url=keep("photo_url", "photoUrl", "studentPhotoUrl"),
        district_id=keep("district_id", "schoolDistrictId", "districtId") or "0",
    )
    if dry_run:
        return {
            "dry_run": True,
            "endpoint": "/updateStudentServlet",
            "payload": payload,
        }
    client.post("/updateStudentServlet", payload)
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
