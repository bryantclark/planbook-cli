"""To-do resource operations."""

from __future__ import annotations

import contextlib

from .. import projection
from ..client import PlanbookClient
from ..errors import ApiError, PlanbookError, SchemaDrift, UsageError
from ..fields import Field, resolve
from ..mutations import (
    Mutation,
    Request,
    commit,
    preview,
    require_intent,
)
from ..narrow import as_id, records
from ..narrow import text as text_of
from ..types import FormPayload, Id, JsonObject, JsonValue, Result, Todo
from ..wire import TODO_PRIORITIES, intish

TODO_FIELDS = (
    Field("text", "toDoText"),
    Field("start_date", "startDate"),
    Field("due_date", "dueDate"),
    Field("priority", "priority", default="1"),
    Field("done", "done", is_flag=True),
    Field("repeats", "repeats", default="daily"),
)


def raw_todos(client: PlanbookClient, *, class_id: str = "all") -> JsonValue:
    """The undecoded `/getToDos` body. Backs `todos list --raw`."""
    return client.post("/getToDos", {"classId": class_id})


def list_todos(client: PlanbookClient, *, class_id: str = "all") -> list[Todo]:
    """To-dos, projected to readable keys."""
    return [projection.todo(t) for t in wire_todos(client, class_id=class_id)]


def wire_todos(client: PlanbookClient, *, class_id: str = "all") -> list[JsonObject]:
    """The wire records, for the read-modify-write path that resends them."""
    body = raw_todos(client, class_id=class_id)
    inner = body["toDos"] if isinstance(body, dict) and "toDos" in body else body
    return records(inner, where="getToDos.toDos")


def _todo_payload(
    *,
    todo_id: Id,
    text: str,
    start_date: str,
    due_date: str,
    priority: str,
    done: str,
    repeats: str,
    class_id: str = "",
) -> FormPayload:
    return {
        # A class-scoped to-do loses its class if this is not resent.
        "subjectId": class_id,
        "startDate": start_date,
        "dueDate": due_date,
        "toDoText": text,
        "priority": priority,
        "done": done,
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
) -> Result:
    """Create a to-do.

    Two writes: `/updateToDo` only issues an id from a bare `action=A`, so the
    empty row is created first and filled in second.
    """

    def payload(todo_id: Id) -> FormPayload:
        return _todo_payload(
            todo_id=todo_id,
            text=text,
            start_date=start,
            due_date=due or start,
            priority=TODO_PRIORITIES.get(priority, priority),
            done="1" if done else "0",
            repeats=repeats,
        )

    if dry_run:
        # The id is only known after the first write, so it reads 0 here.
        return preview(
            Mutation(
                resource="todo",
                operation="create",
                requests=[
                    Request("/updateToDo", {"action": "A"}),
                    Request("/updateToDo", payload(0)),
                ],
            )
        )
    assert client is not None  # only the dry_run branch runs without one
    created = client.post("/updateToDo", {"action": "A"})
    created_record = created if isinstance(created, dict) else {}
    if not created_record.get("toDoId"):
        raise SchemaDrift(
            f"Creating a to-do did not return a toDoId. Response was: {created!r}"
        )
    todo_id = as_id(created_record["toDoId"], where="updateToDo.toDoId")
    try:
        result = commit(
            client,
            Mutation(
                resource="todo",
                operation="create",
                requests=[Request("/updateToDo", payload(todo_id))],
            ),
            # Step one already created the row, so finding it proves nothing.
            read=lambda: find_todo(client, todo_id=todo_id),
        )
    except Exception:
        # Step one created an empty row; leaving it behind puts a blank to-do
        # in the user's list.
        with contextlib.suppress(PlanbookError):
            delete_todo(client, todo_id=todo_id)
        raise
    return {**result, "id": todo_id, "text": text}


def find_todo(client: PlanbookClient, *, todo_id: Id) -> JsonObject | None:
    """The saved to-do, or None. There is no get-one endpoint."""
    for record in wire_todos(client):
        if str(record.get("toDoId")) == str(intish(todo_id)):
            return record
    return None


def update_todo(
    client: PlanbookClient,
    *,
    todo_id: Id,
    text: str | None = None,
    start: str | None = None,
    due: str | None = None,
    priority: str | None = None,
    done: bool | None = None,
    repeats: str | None = None,
    dry_run: bool = False,
) -> Result:
    """Update a to-do, carrying over whatever the caller did not name.

    `/updateToDo` replaces the whole record, so a payload built from defaults
    silently reopens a completed to-do and resets its priority and due date.
    """
    given: dict[str, str | bool | None] = {
        "text": text,
        "start_date": start,
        "due_date": due,
        "priority": None
        if priority is None
        else TODO_PRIORITIES.get(priority, priority),
        "done": done,
        "repeats": repeats,
    }
    if all(value is None for value in given.values()):
        # Checked before the read: once carry-over fills these from the saved
        # to-do, the resend is indistinguishable from a real edit.
        raise UsageError(
            "Nothing to write. Pass at least one of --text, --start, --due, "
            "--priority, --done, --not-done, --repeats."
        )
    existing = find_todo(client, todo_id=todo_id)
    if existing is None:
        raise ApiError(
            f"No to-do with id {todo_id}. Without the current record an update "
            "would blank every field it does not restate."
        )
    edit = resolve(TODO_FIELDS, existing, given)
    if not edit["due_date"]:
        edit.set("due_date", edit["start_date"])
    payload = _todo_payload(
        todo_id=todo_id,
        class_id=text_of(existing, "subjectId", "classId") or "",
        **edit.values,
    )
    mutation = Mutation(
        resource="todo",
        operation="update",
        requests=[Request("/updateToDo", payload)],
        before=projection.todo(existing),
        named=edit.named,
        checks=edit.checks,
        flags=edit.flags,
    )
    if dry_run:
        return preview(mutation)

    result = commit(
        client,
        mutation,
        read=lambda: find_todo(client, todo_id=todo_id),
    )
    return {**result, "id": intish(todo_id)}


def delete_todo(
    client: PlanbookClient,
    *,
    todo_id: Id,
    dry_run: bool = False,
) -> Result:
    mutation = Mutation(
        resource="todo",
        operation="delete",
        requests=[Request("/updateToDo", {"toDoId": intish(todo_id), "action": "D"})],
    )
    if dry_run:
        # Only the preview needs the current record; the real delete does not.
        existing = find_todo(client, todo_id=todo_id)
        mutation.before = projection.todo(existing) if existing else None
        return preview(mutation)
    require_intent(mutation, confirmed=False)
    return commit(
        client,
        mutation,
        verify=lambda: find_todo(client, todo_id=todo_id),
        result={"deleted_todo_id": intish(todo_id)},
    )
