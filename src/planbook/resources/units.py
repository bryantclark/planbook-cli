"""Unit resource operations."""

from __future__ import annotations

from typing import Any

from ..client import PlanbookClient
from ..wire import intish

UNIT_ACTIONS = {"add": "A", "update": "U", "delete": "D"}


def unit_payload(
    *,
    action: str,
    class_id: Any,
    unit_id: Any = 0,
    number: str = "",
    title: str = "",
    description: str = "",
    start: str = "",
    end: str = "",
    lesson_text: str = "",
    homework_text: str = "",
    notes_text: str = "",
    sections: dict[int, str] | None = None,
) -> dict[str, str]:
    section_text = dict(sections or {})
    return {
        "unitId": intish(unit_id),
        "subjectId": intish(class_id),
        "unitNum": number,
        "unitTitle": title,
        "action": action,
        "unitDesc": description,
        "unitStart": start,
        "unitEnd": end,
        "unitLessonText": section_text.get(1, lesson_text),
        "unitHomeworkText": section_text.get(2, homework_text),
        "unitNotesText": section_text.get(3, notes_text),
        "unitSection4Text": section_text.get(4, ""),
        "unitSection5Text": section_text.get(5, ""),
        "unitSection6Text": section_text.get(6, ""),
        "userMode": "T",
        "types": "SS",
    }


def list_units(client: PlanbookClient, *, raw: bool = False) -> Any:
    body = client.post("/getUnits")
    if raw or not isinstance(body, dict):
        return body
    return body.get("units", body)


def create_unit(
    client: PlanbookClient,
    *,
    class_id: Any,
    number: str,
    title: str,
    description: str = "",
    start: str = "",
    end: str = "",
) -> Any:
    payload = unit_payload(
        action="A",
        class_id=class_id,
        number=number,
        title=title,
        description=description,
        start=start,
        end=end,
    )

    # /updateUnit does not report the new id. Diff the class's units around the
    # write so the caller gets a unit_id to update or delete.
    def unit_ids() -> set[str]:
        return {
            str(u.get("unitId"))
            for u in (list_units(client) or [])
            if isinstance(u, dict) and str(u.get("subjectId")) == str(intish(class_id))
        }

    before = unit_ids()
    client.post("/updateUnit", payload)
    created = unit_ids() - before
    return {
        "ok": True,
        "class_id": payload["subjectId"],
        "number": number,
        "title": title,
        "unit_id": created.pop() if len(created) == 1 else None,
    }


def find_unit(client: PlanbookClient, *, unit_id: Any) -> dict[str, Any] | None:
    """The saved unit, or None. There is no get-one endpoint."""
    for record in list_units(client) or []:
        if isinstance(record, dict) and str(record.get("unitId")) == str(
            intish(unit_id)
        ):
            return record
    return None


def update_unit(
    client: PlanbookClient,
    *,
    unit_id: Any,
    class_id: Any,
    number: str | None = None,
    title: str | None = None,
    description: str | None = None,
    start: str | None = None,
    end: str | None = None,
    dry_run: bool = False,
) -> Any:
    """Update a unit, carrying over whatever the caller did not name.

    `/updateUnit` replaces the whole record, so a payload built from defaults
    blanks the description, dates and all six section texts. Read-modify-write,
    the same as a lesson.
    """
    existing = find_unit(client, unit_id=unit_id) or {}
    sections = {
        n: str(existing.get(field) or "")
        for n, field in enumerate(
            (
                "unitLessonText",
                "unitHomeworkText",
                "unitNotesText",
                "unitSection4Text",
                "unitSection5Text",
                "unitSection6Text",
            ),
            start=1,
        )
        if existing.get(field)
    }

    def keep(value: Any, *names: str) -> str:
        if value is not None:
            return str(value)
        for name in names:
            if existing.get(name) not in (None, ""):
                return str(existing[name])
        return ""

    payload = unit_payload(
        action="U",
        class_id=class_id,
        unit_id=unit_id,
        number=keep(number, "unitNum"),
        title=keep(title, "unitTitle"),
        description=keep(description, "unitDesc"),
        start=keep(start, "unitStart"),
        end=keep(end, "unitEnd"),
        sections=sections or None,
    )
    if dry_run:
        return {"dry_run": True, "endpoint": "/updateUnit", "payload": payload}
    client.post("/updateUnit", payload)
    return {"ok": True, "unit_id": payload["unitId"], "title": payload["unitTitle"]}


def delete_unit(
    client: PlanbookClient,
    *,
    unit_id: Any,
    class_id: Any,
) -> Any:
    payload = unit_payload(action="D", class_id=class_id, unit_id=unit_id)
    client.post("/updateUnit", payload)
    return {"ok": True, "deleted_unit_id": payload["unitId"]}
