"""Unit resource operations."""

from __future__ import annotations

from .. import projection
from ..client import PlanbookClient
from ..errors import ApiError, UsageError
from ..fields import Field, resolve
from ..mutations import (
    Mutation,
    Request,
    commit,
    preview,
    require_intent,
    resolve_created,
)
from ..narrow import records
from ..types import FormPayload, Id, JsonObject, JsonValue, Result, Unit
from ..wire import UNIT_SECTION_FIELDS, intish

UNIT_ACTIONS = {"add": "A", "update": "U", "delete": "D"}

UNIT_FIELDS = (
    Field("number", "unitNum"),
    Field("title", "unitTitle"),
    Field("description", "unitDesc"),
    Field("start_date", "unitStart"),
    Field("end_date", "unitEnd"),
)


def unit_payload(
    *,
    action: str,
    class_id: Id,
    unit_id: Id = 0,
    number: str = "",
    title: str = "",
    description: str = "",
    start_date: str = "",
    end_date: str = "",
    lesson_text: str = "",
    homework_text: str = "",
    notes_text: str = "",
    sections: dict[int, str] | None = None,
) -> FormPayload:
    section_text = dict(sections or {})
    return {
        "unitId": intish(unit_id),
        "subjectId": intish(class_id),
        "unitNum": number,
        "unitTitle": title,
        "action": action,
        "unitDesc": description,
        "unitStart": start_date,
        "unitEnd": end_date,
        **{
            field: section_text.get(n, default)
            for (n, field), default in zip(
                UNIT_SECTION_FIELDS.items(),
                (lesson_text, homework_text, notes_text, "", "", ""),
                strict=True,
            )
        },
        "userMode": "T",
        "types": "SS",
    }


def raw_units(client: PlanbookClient) -> JsonValue:
    """The undecoded `/getUnits` body. Backs `units list --raw`."""
    return client.post("/getUnits")


def list_units(client: PlanbookClient) -> list[Unit]:
    """Units, projected to readable keys."""
    return [projection.unit(u) for u in wire_units(client)]


def wire_units(client: PlanbookClient) -> list[JsonObject]:
    """The wire records, for the read-modify-write paths that resend them."""
    body = raw_units(client)
    inner = body.get("units", body) if isinstance(body, dict) else body
    return records(inner, where="getUnits.units")


def create_unit(
    client: PlanbookClient | None,
    *,
    class_id: Id,
    number: str,
    title: str,
    description: str = "",
    start: str = "",
    end: str = "",
    dry_run: bool = False,
) -> Result:
    payload = unit_payload(
        action="A",
        class_id=class_id,
        number=number,
        title=title,
        description=description,
        start_date=start,
        end_date=end,
    )
    mutation = Mutation(
        resource="unit",
        operation="create",
        requests=[Request("/updateUnit", payload)],
    )
    if dry_run:
        return preview(mutation)
    assert client is not None  # only the dry_run branch runs without one

    owner = str(intish(class_id))

    def ids() -> set[str]:
        return {
            str(u.get("unitId"))
            for u in wire_units(client)
            if str(u.get("subjectId")) == owner
        }

    # /updateUnit does not report the new id, so diff the class's units around
    # the write and narrow by what was written.
    before = ids()
    result = commit(client, mutation)
    unit_id = resolve_created(
        resource="unit",
        before=before,
        after=[u for u in wire_units(client) if str(u.get("subjectId")) == owner],
        id_of=lambda u: u.get("unitId"),
        matches=lambda u: (
            str(u.get("unitNum")) == str(number)
            and str(u.get("unitTitle")) == str(title)
        ),
        list_command=f"planbook units list --class-id {owner}",
    )
    return {
        **result,
        "class_id": owner,
        "number": number,
        "title": title,
        "id": unit_id,
    }


def require_unit(client: PlanbookClient, *, unit_id: Id, class_id: Id) -> JsonObject:
    unit = find_unit(client, unit_id=unit_id)
    if unit is None:
        raise ApiError(f"No unit with id {unit_id}. Run `planbook units list`.")
    _require_owner(unit, unit_id=unit_id, class_id=class_id)
    return unit


def _require_owner(unit: JsonObject, *, unit_id: Id, class_id: Id) -> None:
    # subjectId is written from --class-id; a mismatch silently moves the unit.
    owner = unit.get("subjectId")
    if owner is not None and str(owner) != str(intish(class_id)):
        raise UsageError(
            f"Unit {unit_id} belongs to class {owner}, not {intish(class_id)}. "
            "Pass the class the unit is in."
        )


def find_unit(client: PlanbookClient, *, unit_id: Id) -> JsonObject | None:
    """The saved unit, or None. There is no get-one endpoint."""
    for record in wire_units(client):
        if str(record.get("unitId")) == str(intish(unit_id)):
            return record
    return None


def update_unit(
    client: PlanbookClient,
    *,
    unit_id: Id,
    class_id: Id,
    number: str | None = None,
    title: str | None = None,
    description: str | None = None,
    start: str | None = None,
    end: str | None = None,
    dry_run: bool = False,
) -> Result:
    """Update a unit, carrying over whatever the caller did not name."""
    existing = find_unit(client, unit_id=unit_id)
    if existing is None:
        raise ApiError(
            f"No unit with id {unit_id}. Without the current record an update "
            "would blank the description, dates and section texts it does not "
            "restate."
        )
    _require_owner(existing, unit_id=unit_id, class_id=class_id)
    sections = {
        n: str(existing[field])
        for n, field in UNIT_SECTION_FIELDS.items()
        if existing.get(field)
    }

    given: dict[str, str | bool | None] = {
        "number": number,
        "title": title,
        "description": description,
        "start_date": start,
        "end_date": end,
    }
    edit = resolve(UNIT_FIELDS, existing, given)
    payload = unit_payload(
        action="U",
        class_id=class_id,
        unit_id=unit_id,
        sections=sections or None,
        **edit.values,
    )
    mutation = Mutation(
        resource="unit",
        operation="update",
        requests=[Request("/updateUnit", payload)],
        before=projection.unit(existing),
        named=edit.named,
        checks=edit.checks,
        flags=edit.flags,
    )
    if dry_run:
        return preview(mutation)

    result = commit(
        client,
        mutation,
        read=lambda: find_unit(client, unit_id=unit_id),
    )
    return {
        **result,
        "id": payload["unitId"],
        "title": payload["unitTitle"],
    }


def delete_unit(
    client: PlanbookClient,
    *,
    unit_id: Id,
    class_id: Id,
    dry_run: bool = False,
) -> Result:
    existing = require_unit(client, unit_id=unit_id, class_id=class_id)
    payload = unit_payload(action="D", class_id=class_id, unit_id=unit_id)
    mutation = Mutation(
        resource="unit",
        operation="delete",
        requests=[Request("/updateUnit", payload)],
        before=projection.unit(existing),
    )
    if dry_run:
        return preview(mutation)
    require_intent(mutation, confirmed=False)

    result = commit(client, mutation, verify=lambda: find_unit(client, unit_id=unit_id))
    return {**result, "deleted_unit_id": payload["unitId"]}
