"""Students, attendance and grades.

Students are account-wide; a class sees the subset enrolled in it. Attendance
is read-only: no write endpoint exists under that path.
"""

from __future__ import annotations

from .. import projection
from ..client import PlanbookClient
from ..errors import ApiError, SchemaDrift, UsageError
from ..fields import Field, resolve
from ..mutations import (
    Mutation,
    Request,
    commit,
    preview,
    require_intent,
    resolve_created,
)
from ..narrow import as_object, records, unwrap
from ..types import Id, JsonObject, JsonValue, Result, Student, Template
from ..wire import intish

STUDENT_FIELDS = (
    Field("first_name", "studentFirstName", ("firstName", "studentFirstName")),
    Field("last_name", "studentLastName", ("lastName", "studentLastName")),
    Field("code", "studentCode", ("code", "studentCode")),
    Field("email", "studentEmailAddress", ("emailAddress", "studentEmailAddress")),
    Field("phone", "studentPhoneNumber", ("phoneNumber", "studentPhoneNumber")),
    Field("parent_email", "parentEmailAddress", ("parentEmailAddress",)),
    Field("birthdate", "studentBirthDate", ("birthDate", "studentBirthDate")),
    Field("middle_name", "studentMiddleName", ("middleName", "studentMiddleName")),
    Field("gender", "studentGender", ("gender", "studentGender")),
)

#: Carried over but never verified: `district_id` falls back to "0", which a
#: read-back would not find.
CARRIED_STUDENT_FIELDS = (
    Field("photo_url", "studentPhotoUrl", ("photoUrl", "studentPhotoUrl")),
    Field("district_id", "schoolDistrictId", ("schoolDistrictId", "districtId")),
)


def list_students(
    client: PlanbookClient, *, class_id: Id | None = None
) -> list[Student]:
    """Students in one class, or every student on the account.

    The account-wide endpoint answers `{id: "Last, First"}`; the per-class one
    returns full records, so the two carry different fields. Both key on `id`.
    """
    if class_id is None:
        return [
            Student(
                id=r["id"],
                name=r["name"],
                last_name=r["last_name"],
            )
            for r in _account_roster(client)
        ]
    return [projection.student(s) for s in _class_students(client, class_id)]


def _account_roster(client: PlanbookClient) -> list[JsonObject]:
    """Every student on the account. This endpoint answers `{id: "Last, First"}`."""
    body = as_object(
        client.post("/services/planbook/student/getAllFromSchool"),
        where="getAllFromSchool",
    )
    if not all(str(k).lstrip("-").isdigit() for k in body):
        raise SchemaDrift("getAllFromSchool returned a non-id key.")
    return [
        {"id": int(k), "name": v, "last_name": str(v).split(",")[0].strip()}
        for k, v in body.items()
    ]


def _class_students(client: PlanbookClient, class_id: Id) -> list[JsonObject]:
    """The wire records for one class.

    A missing `students` list is drift (exit 65), not an empty class.
    """
    body = as_object(
        client.post(
            "/getStudentsServlet", {"classId": intish(class_id), "userMode": "T"}
        ),
        where="getStudentsServlet",
    )
    if "students" not in body:
        raise SchemaDrift("getStudentsServlet returned no `students` list.")
    return records(body["students"], where="getStudentsServlet.students")


def student_payload(
    *,
    first_name: str,
    last_name: str,
    student_id: Id = 0,
    code: str = "",
    email: str = "",
    phone: str = "",
    parent_email: str = "",
    birthdate: str = "",
    middle_name: str = "",
    gender: str = "",
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
        # Another full-replace field. `/getStudentsServlet` returns it, so
        # omitting it here blanks it on an unrelated edit.
        "studentGender": gender,
        "schoolDistrictId": district_id or "0",
        "userMode": "T",
        # A full-replace endpoint: a saved photo is lost unless carried over.
        "studentPhotoUrl": photo_url,
    }
    if student_id:
        payload["studentId"] = intish(student_id)
    return payload


def create_student(
    client: PlanbookClient | None, *, dry_run: bool = False, **fields: str
) -> Result:
    payload = student_payload(**fields)
    mutation = Mutation(
        resource="student",
        operation="create",
        requests=[Request("/addStudentServlet", payload)],
    )
    if dry_run:
        return preview(mutation)

    assert client is not None  # only the dry_run branch runs without one

    # /addStudentServlet does not report the new id, so diff the account roster
    # around the write and narrow by the name written.
    def roster() -> list[JsonObject]:
        return [s for s in _account_roster(client) if s.get("id") is not None]

    name = f"{fields['first_name']} {fields['last_name']}"
    listed = f"{fields['last_name']}, {fields['first_name']}"
    before = {str(s.get("id")) for s in roster()}
    result = commit(client, mutation)
    student_id = resolve_created(
        resource="student",
        before=before,
        after=roster(),
        id_of=lambda s: s.get("id"),
        matches=lambda s: str(s.get("name") or "").strip() == listed,
        list_command="planbook students list",
    )
    return {**result, "name": name, "id": student_id}


def find_student(
    client: PlanbookClient, *, student_id: Id, class_id: Id
) -> JsonObject | None:
    """The raw student record from the per-class endpoint, or None.

    There is no get-one endpoint, so a full record needs the class the student
    sits in.
    """
    for record in _class_students(client, class_id):
        identity = record.get("studentId") or record.get("id")
        if str(identity) == str(intish(student_id)):
            return record
    return None


def update_student(
    client: PlanbookClient,
    *,
    student_id: Id,
    class_id: Id,
    dry_run: bool = False,
    **fields: str | None,
) -> Result:
    """Update a student, carrying over whatever the caller did not name.

    `/updateStudentServlet` replaces the whole record, so a payload built from
    defaults blanks the email, phone, parent email, code and birthdate. Reads
    the current record first, keyed by the class the student is in.
    """
    if all(value is None for value in fields.values()):
        # Checked before the read: once carry-over fills these from the saved
        # student, the resend is indistinguishable from a real edit.
        raise UsageError(
            "Nothing to write. Pass at least one of --first-name, --last-name, "
            "--middle-name, --code, --email, --parent-email, --phone, "
            "--birthdate."
        )
    existing = find_student(client, student_id=student_id, class_id=class_id)
    if existing is None:
        raise ApiError(
            f"No student {student_id} in class {class_id}. Pass the --class-id "
            "the student is in so their other fields are not lost."
        )

    edit = resolve(STUDENT_FIELDS, existing, fields)
    carried = resolve(CARRIED_STUDENT_FIELDS, existing, fields)
    payload = student_payload(
        student_id=student_id,
        **edit.values,
        **carried.values,
    )
    mutation = Mutation(
        resource="student",
        operation="update",
        requests=[Request("/updateStudentServlet", payload)],
        before={
            "id": intish(student_id),
            "first_name": existing.get("firstName"),
            "last_name": existing.get("lastName"),
            "code": existing.get("code"),
            "email": existing.get("emailAddress"),
        },
        named=edit.named,
        checks=edit.checks,
        flags=edit.flags,
    )
    if dry_run:
        return preview(mutation)

    result = commit(
        client,
        mutation,
        read=lambda: find_student(client, student_id=student_id, class_id=class_id),
    )
    return {**result, "id": intish(student_id)}


def delete_student(
    client: PlanbookClient,
    *,
    student_id: Id,
    class_id: Id | None = None,
    dry_run: bool = False,
) -> Result:
    payload = {"studentId": intish(student_id), "userMode": "T"}
    mutation = Mutation(
        resource="student",
        operation="delete",
        requests=[Request("/deleteStudentServlet", payload)],
    )
    if dry_run:
        if class_id is not None:
            existing = find_student(client, student_id=student_id, class_id=class_id)
            if existing is not None:
                mutation.before = {
                    "id": intish(student_id),
                    "first_name": existing.get("firstName"),
                    "last_name": existing.get("lastName"),
                }
        return preview(mutation)
    require_intent(mutation, confirmed=False)
    return commit(
        client,
        mutation,
        # No get-one endpoint, so the read-back needs the student's class.
        verify=(
            None
            if class_id is None
            else lambda: find_student(client, student_id=student_id, class_id=class_id)
        ),
        result={"deleted_student_id": intish(student_id)},
    )


def get_attendance(client: PlanbookClient, *, class_id: Id, date: str) -> JsonValue:
    """Attendance for one class on one date. GET-only, and there is no write
    endpoint under the same path."""
    return client.get(
        "/services/planbook/attendance/get",
        {"classId": intish(class_id), "date": date},
    )


def get_scores(client: PlanbookClient, *, class_id: Id) -> JsonValue:
    """Grade periods and assignments with scores for one class."""
    return client.post(
        "/getStudentScoresServlet",
        {"classId": intish(class_id), "subjectId": intish(class_id), "userMode": "T"},
    )


def raw_templates(client: PlanbookClient, *, teacher_id: Id) -> JsonValue:
    """The undecoded template body. Backs `templates --raw`."""
    return client.get(
        "/services/planbook/template/get", {"teacherId": intish(teacher_id)}
    )


def list_templates(client: PlanbookClient, *, teacher_id: Id) -> list[Template]:
    return [
        projection.template(t)
        for t in unwrap(
            raw_templates(client, teacher_id=teacher_id),
            "templates",
            where="template/get",
            required=False,
        )
    ]
