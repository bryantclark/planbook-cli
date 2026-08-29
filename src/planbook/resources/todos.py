"""To-do resource operations."""

from __future__ import annotations

import contextlib
from typing import Any

from ..client import PlanbookClient
from ..errors import PlanbookError, SchemaDrift
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
    client: PlanbookClient,
    *,
    text: str,
    start: str,
    due: str = "",
    priority: str = "low",
    done: bool = False,
    repeats: str = "daily",
) -> dict[str, Any]:
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
    except PlanbookError:
        # Step one already created an empty row. Leaving it behind would put
        # a blank to-do in the user's list with no sign of where it came from.
        with contextlib.suppress(PlanbookError):
            delete_todo(client, todo_id=todo_id)
        raise
    return {"ok": True, "todo_id": todo_id, "text": text}


def update_todo(
    client: PlanbookClient,
    *,
    todo_id: Any,
    text: str,
    start: str,
    due: str = "",
    priority: str = "low",
    done: bool = False,
    repeats: str = "daily",
) -> dict[str, Any]:
    client.post(
        "/updateToDo",
        _todo_payload(
            todo_id=todo_id,
            text=text,
            start=start,
            due=due,
            priority=priority,
            done=done,
            repeats=repeats,
        ),
    )
    return {"ok": True, "todo_id": intish(todo_id)}


def delete_todo(client: PlanbookClient, *, todo_id: Any) -> dict[str, Any]:
    client.post("/updateToDo", {"toDoId": intish(todo_id), "action": "D"})
    return {"ok": True, "deleted_todo_id": intish(todo_id)}
