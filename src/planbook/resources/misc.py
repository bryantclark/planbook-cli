"""Miscellaneous read endpoints and attachment helpers."""

from __future__ import annotations

from pathlib import Path

from ..client import PlanbookClient
from ..errors import SchemaDrift, UsageError
from ..mutations import Mutation, Request, preview
from ..narrow import as_object, records
from ..types import (
    Attachment,
    AttachmentLink,
    FormPayload,
    Id,
    JsonObject,
    JsonValue,
    Result,
    Standard,
)
from ..wire import intish


def list_assignments(client: PlanbookClient) -> list[JsonObject]:
    """Assignments, unwrapped from their envelope."""
    return _unwrap_records(client.post("/getAssignments"), "assignments")


def _unwrap_records(body: JsonValue, key: str) -> list[JsonObject]:
    """The records under `key`, when the body is that single-key envelope."""
    if isinstance(body, dict) and set(body) == {key}:
        return records(body[key], where=key)
    return records(body, where=key)


def special_days(
    client: PlanbookClient, *, teacher_id: Id, year_id: Id, school_id: Id = 0
) -> JsonValue:
    return client.post(
        "/getSpecialDays",
        {
            "teacherId": intish(teacher_id),
            "yearId": intish(year_id),
            "schoolId": intish(school_id),
        },
    )


def settings(client: PlanbookClient) -> JsonValue:
    return client.post("/getSettings")


def raw_standards(client: PlanbookClient) -> JsonValue:
    """The undecoded `/getStandards` body. Backs `standards --raw`."""
    return client.post("/getStandards")


def standards(client: PlanbookClient, *, search: str = "") -> list[Standard]:
    """Standards available to the account.

    `dbId` is what attaches a standard to a lesson; the human `id` (like
    "3.NBT.A.1") is not accepted by the write path.
    """
    items = records(
        as_object(raw_standards(client), where="getStandards").get("standards") or [],
        where="getStandards.standards",
    )
    out = [
        Standard(
            db_id=st.get("dbId"),
            id=st.get("sI") or st.get("id"),
            description=st.get("sD") or st.get("desc"),
            subject=st.get("subject"),
            category=st.get("category"),
        )
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


# Read-only endpoints taking no arguments. name -> (path, key to unwrap)
SIMPLE_READS: dict[str, tuple[str, str | None]] = {
    "assignments": ("/getAssignments", "assignments"),
    "assessments": ("/getAssessments", "assessments"),
    "schools": ("/getSchools", "schools"),
    "students": ("/services/planbook/student/getAllFromSchool", None),
    "comments": ("/getCommentsTo", None),
}
# /getStandardsReport and /services/planbook/newNote/filterNotes are missing on
# purpose: each demands an integer parameter the server will not name. Reachable
# through `planbook raw` once a real request has been captured.


def simple_read(
    client: PlanbookClient,
    name: str,
    *,
    raw: bool = False,
    extra: FormPayload | None = None,
) -> JsonValue:
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


def upload(
    client: PlanbookClient,
    file_path: str,
    *,
    dry_run: bool = False,
    replaces: bool | None = False,
) -> Result:
    """Upload one file, through the seam like every other write.

    `replaces` says the account already holds this name, so the upload
    overwrites the stored file in every lesson linked to it. `None` means the
    lookup failed, reported as a null: "could not check" and "replaces
    nothing" must not be the same answer. The caller reads
    the list once for the whole batch, so nothing here costs a request.
    """
    path = Path(file_path)
    if not path.is_file():
        raise UsageError(f"No such file: {file_path}")
    name = path.name
    mutation = Mutation(
        resource="attachment",
        operation="create",
        # The real send is multipart, not a form field; say so in the preview.
        requests=[
            Request("/uploadAttachment", {"file": name, "encoding": "multipart"})
        ],
        effects=_replacement(name, replaces),
    )
    if dry_run:
        return preview(mutation)
    link = upload_attachment(client, file_path)
    # `upload_attachment` fails on a response without a fileURL, which is this
    # endpoint's postcondition - there is nothing further to read back.
    result: Result = {"ok": True, "updated_fields": []}
    if mutation.effects:
        result["effects"] = mutation.effects
    return {**result, **dict(link)}


def _replacement(name: str, replaces: bool | None) -> Result:
    """The `effects` entry for a name this upload may overwrite.

    Absent means it replaces nothing. `null` means the lookup failed - not a
    string, because a string is iterable and a caller looping the names would
    silently get characters instead of failing.
    """
    if replaces is None:
        return {"replaces_existing": None}
    return {"replaces_existing": [name]} if replaces else {}


def upload_attachment(client: PlanbookClient, file_path: str) -> AttachmentLink:
    """Upload a file to the account's resources.

    The lesson stores the signed URL itself, so re-uploading a file under the
    same name replaces it everywhere it is linked.
    """
    path = Path(file_path)
    body = client.upload("/uploadAttachment", str(path))
    if not isinstance(body, dict) or "fileURL" not in body:
        raise SchemaDrift(f"uploadAttachment returned {body!r}")
    return AttachmentLink(
        name=str(body.get("fileName") or path.name), url=str(body["fileURL"])
    )


def list_attachments(client: PlanbookClient, *, teacher_id: Id) -> list[Attachment]:
    body = as_object(
        attachments(client, teacher_id=teacher_id), where="getAttachmentList"
    )
    return [
        Attachment(name=f.get("fileKey"), url=f.get("fileUrl"), size=f.get("fileSize"))
        for f in records(body.get("fileList") or [], where="getAttachmentList.fileList")
    ]


def resolve_attachment(
    client: PlanbookClient, reference: str, *, teacher_id: Id
) -> AttachmentLink:
    """Turn a local path or an existing resource name into name+URL.

    A path that exists on disk is uploaded; anything else is looked up among
    the account's existing resources.
    """
    if Path(reference).is_file():
        return upload_attachment(client, reference)
    for item in list_attachments(client, teacher_id=teacher_id):
        if item["name"] == reference:
            return AttachmentLink(name=str(item["name"]), url=str(item["url"]))
    raise UsageError(
        f"{reference!r} is neither a file on disk nor an existing resource. "
        "See `planbook attachments list`."
    )


def resolve_attachments(
    client: PlanbookClient, references: list[str], *, teacher_id: Id
) -> list[AttachmentLink]:
    """Resolve several --attach refs, validating all before uploading any.

    Uploading is a side effect, so a bad ref halfway through would leave
    earlier files uploaded with nothing linking them.
    """
    known = {
        str(item["name"])
        for item in list_attachments(client, teacher_id=teacher_id)
        if item["name"] is not None
    }
    unknown = [
        ref for ref in references if not Path(ref).is_file() and ref not in known
    ]
    if unknown:
        raise UsageError(
            f"{', '.join(repr(r) for r in unknown)}: neither a file on disk nor "
            "an existing resource. Nothing was uploaded. "
            "See `planbook attachments list`."
        )
    return [
        resolve_attachment(client, ref, teacher_id=teacher_id) for ref in references
    ]


def attachments(client: PlanbookClient, *, teacher_id: Id) -> JsonValue:
    return client.post(
        "/getAttachmentList",
        {
            "teacherId": intish(teacher_id),
            "isFolderStructured": "true",
            "withAllFolders": "true",
        },
    )
