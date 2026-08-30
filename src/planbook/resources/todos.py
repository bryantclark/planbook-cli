"""To-do resource operations."""

from __future__ import annotations

import contextlib
from typing import Any

from ..client import PlanbookClient
from ..errors import ApiError, PlanbookError, SchemaDrift
from ..wire import intish

TODO_PRIORITIES = {"low": "1", "medium": "2", "high": "3"}


def list_todos(client: PlanbookClient, *, class_id: str = "all") -> Any:
    body = client.post("/getToDos", {"classId": class_id})
    if isinstance(body, dict) and set(body) == {"toDos"}:
        return body["toDos"]
    return body


def _todo_payload(
    *,
    todo_id: Any,
    text: str,
    start: str,
    due: str,
    priority: str,
    done: bool,
    repeats: str = "daily",
) -> dict[str, str]:
    return {
        "startDate": start,
        "dueDate": due or start,
        "toDoText": text,
        "priority": TODO_PRIORITIES.get(priority, priority),
        "done": "1" if done else "0",
        "toDoId": intish(todo_id),
        "repeats": repeats,
        "currentDate": "",
        "updateCurrentTodo": "false",
        "action": "U",
    }


def create_todo(
    client: PlanbookClient | None,
    *,
    text: str,
    start: str,
    due: str = "",
    priority: str = "low",
    done: bool = False,
    repeats: str = "daily",
    dry_run: bool = False,
) -> dict[str, Any]:
    if dry_run:
        # Show the second write's payload; the id is only known after the
        # create, so it reads 0 here. No row is created.
        payload = _todo_payload(
            todo_id=0,
            text=text,
            start=start,
            due=due,
            priority=priority,
            done=done,
            repeats=repeats,
        )
        return {"dry_run": True, "endpoint": "/updateToDo", "payload": payload}
    assert client is not None  # only the dry_run branch runs without one
    created = client.post("/updateToDo", {"action": "A"})
    todo_id = None
    if isinstance(created, dict):
        todo_id = created.get("toDoId")
    if not todo_id:
        raise SchemaDrift(
            f"Creating a to-do did not return a toDoId. Response was: {created!r}"
        )
    payload = _todo_payload(
        todo_id=todo_id,
        text=text,
        start=start,
        due=due,
        priority=priority,
        done=done,
        repeats=repeats,
    )
    try:
        client.post("/updateToDo", payload)
    except Exception:
        # Step one already created an empty row. Leaving it behind would put
        # a blank to-do in the user's list with no sign of where it came from.
        with contextlib.suppress(PlanbookError):
            delete_todo(client, todo_id=todo_id)
        raise
    return {"ok": True, "todo_id": todo_id, "text": text}


PRIORITY_NAMES = {v: k for k, v in TODO_PRIORITIES.items()}


def find_todo(client: PlanbookClient, *, todo_id: Any) -> dict[str, Any] | None:
    """The saved to-do, or None. There is no get-one endpoint."""
    for record in list_todos(client) or []:
        if isinstance(record, dict) and str(record.get("toDoId")) == str(
            intish(todo_id)
        ):
            return record
    return None


def update_todo(
    client: PlanbookClient,
    *,
    todo_id: Any,
    text: str | None = None,
    start: str | None = None,
    due: str | None = None,
    priority: str | None = None,
    done: bool | None = None,
    repeats: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Update a to-do, carrying over whatever the caller did not name.

    `/updateToDo` replaces the whole record, so a payload built from defaults
    silently reopens a completed to-do and resets its priority and due date.
    Read-modify-write, the same as a lesson.
    """
    existing = find_todo(client, todo_id=todo_id)
    if existing is None:
        raise ApiError(
            f"No to-do with id {todo_id}. Without the current record an update "
            "would blank every field it does not restate."
        )
    if text is None:
        text = str(existing.get("toDoText") or "")
    if start is None:
        start = str(existing.get("startDate") or "")
    if due is None:
        due = str(existing.get("dueDate") or "")
    if priority is None:
        priority = PRIORITY_NAMES.get(
            str(existing.get("priority")), str(existing.get("priority") or "1")
        )
    if done is None:
        done = str(existing.get("done")) in ("1", "true", "True")
    if repeats is None:
        repeats = str(existing.get("repeats") or "daily")
    payload = _todo_payload(
        todo_id=todo_id,
        text=text or "",
        start=start or "",
        due=due or "",
        priority=priority or "low",
        done=bool(done),
        repeats=repeats or "daily",
    )
    if dry_run:
        return {"dry_run": True, "endpoint": "/updateToDo", "payload": payload}
    client.post("/updateToDo", payload)
    return {"ok": True, "todo_id": intish(todo_id)}


def delete_todo(client: PlanbookClient, *, todo_id: Any) -> dict[str, Any]:
    client.post("/updateToDo", {"toDoId": intish(todo_id), "action": "D"})
    return {"ok": True, "deleted_todo_id": intish(todo_id)}
