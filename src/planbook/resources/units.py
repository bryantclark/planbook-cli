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
    client.post("/updateUnit", payload)
    return {
        "ok": True,
        "class_id": payload["subjectId"],
        "number": number,
        "title": title,
    }


def update_unit(
    client: PlanbookClient,
    *,
    unit_id: Any,
    class_id: Any,
    number: str,
    title: str,
    description: str = "",
    start: str = "",
    end: str = "",
) -> Any:
    payload = unit_payload(
        action="U",
        class_id=class_id,
        unit_id=unit_id,
        number=number,
        title=title,
        description=description,
        start=start,
        end=end,
    )
    client.post("/updateUnit", payload)
    return {"ok": True, "unit_id": payload["unitId"], "title": title}


def delete_unit(
    client: PlanbookClient,
    *,
    unit_id: Any,
    class_id: Any,
) -> Any:
    payload = unit_payload(action="D", class_id=class_id, unit_id=unit_id)
    client.post("/updateUnit", payload)
    return {"ok": True, "deleted_unit_id": payload["unitId"]}


# ---------------------------------------------------------------------------
# To-dos
#
# Creating one takes two calls, as the web app does: action "A" mints an empty
# row and returns its id, then "U" fills it in. There is no single-shot create.
