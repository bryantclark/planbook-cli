"""Miscellaneous read endpoints and attachment helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..client import PlanbookClient
from ..errors import SchemaDrift, UsageError
from ..wire import intish


def list_assignments(client: PlanbookClient) -> Any:
    body = client.post("/getAssignments")
    if isinstance(body, dict) and set(body) == {"assignments"}:
        return body["assignments"]
    return body


def special_days(
    client: PlanbookClient, *, teacher_id: Any, year_id: Any, school_id: Any = 0
) -> Any:
    return client.post(
        "/getSpecialDays",
        {
            "teacherId": intish(teacher_id),
            "yearId": intish(year_id),
            "schoolId": intish(school_id),
        },
    )


def settings(client: PlanbookClient) -> Any:
    return client.post("/getSettings")


def standards(client: PlanbookClient, *, search: str = "", raw: bool = False) -> Any:
    """Standards available to the account.

    `dbId` is what attaches a standard to a lesson; the human `id` (like
    "3.NBT.A.1") is not accepted by the write path.
    """
    body = client.post("/getStandards")
    if raw or not isinstance(body, dict):
        return body
    items = body.get("standards") or []
    out = [
        {
            "db_id": st.get("dbId"),
            "id": st.get("sI") or st.get("id"),
            "description": st.get("sD") or st.get("desc"),
            "subject": st.get("subject"),
            "category": st.get("category"),
        }
        for st in items
    ]
    if search:
        needle = search.lower()
        out = [
            o
            for o in out
            if needle in str(o["id"]).lower() or needle in str(o["description"]).lower()
        ]
    return out


# Read-only endpoints taking no arguments.  name -> (path, key to unwrap)
SIMPLE_READS: dict[str, tuple[str, str | None]] = {
    "assignments": ("/getAssignments", "assignments"),
    "assessments": ("/getAssessments", "assessments"),
    "schools": ("/getSchools", "schools"),
    "notes": ("/services/planbook/newNote/filterNotes", None),
    "students": ("/services/planbook/student/getAllFromSchool", None),
    "standards-report": ("/getStandardsReport", None),
    "comments": ("/getCommentsTo", None),
}


def simple_read(
    client: PlanbookClient,
    name: str,
    *,
    raw: bool = False,
    extra: dict[str, Any] | None = None,
) -> Any:
    """Fetch one of the argument-free read endpoints.

    Most wrap a single array in a single key; that envelope is unwrapped
    unless `raw`, so callers get the list rather than something to dig through.
    """
    path, unwrap = SIMPLE_READS[name]
    body = client.post(path, extra or {})
    if raw or unwrap is None or not isinstance(body, dict):
        return body
    if unwrap in body and len(body) == 1:
        return body[unwrap]
    return body


def upload_attachment(client: PlanbookClient, file_path: str) -> dict[str, Any]:
    """Upload a file to the account's resources.

    Returns the stored name and a signed S3 URL. Both are needed to attach it
    to a lesson, and the URL is what the lesson stores - so re-uploading a
    file with the same name replaces it everywhere it is linked.
    """
    path = Path(file_path)
    if not path.is_file():
        raise UsageError(f"No such file: {file_path}")
    body = client.upload("/uploadAttachment", str(path))
    if not isinstance(body, dict) or "fileURL" not in body:
        raise SchemaDrift(f"uploadAttachment returned {body!r}")
    return {"name": body.get("fileName") or path.name, "url": body["fileURL"]}


def list_attachments(client: PlanbookClient, *, teacher_id: Any) -> Any:
    body = attachments(client, teacher_id=teacher_id)
    if isinstance(body, dict) and "fileList" in body:
        return [
            {
                "name": f.get("fileKey"),
                "url": f.get("fileUrl"),
                "size": f.get("fileSize"),
            }
            for f in body["fileList"]
        ]
    return body


def resolve_attachment(
    client: PlanbookClient, reference: str, *, teacher_id: Any
) -> dict[str, str]:
    """Turn a local path or an existing resource name into name+URL.

    A path that exists on disk is uploaded; anything else is looked up among
    the account's existing resources.
    """
    if Path(reference).is_file():
        return upload_attachment(client, reference)
    for item in list_attachments(client, teacher_id=teacher_id) or []:
        if item.get("name") == reference:
            return {"name": item["name"], "url": item["url"]}
    raise UsageError(
        f"{reference!r} is neither a file on disk nor an existing resource. "
        "See `planbook attachments list`."
    )


def attachments(client: PlanbookClient, *, teacher_id: Any) -> Any:
    return client.post(
        "/getAttachmentList",
        {
            "teacherId": intish(teacher_id),
            "isFolderStructured": "true",
            "withAllFolders": "true",
        },
    )
