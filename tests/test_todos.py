"""The to-do resource."""

import urllib.parse

import pytest
import responses

from conftest import (
    stub,
    todo_list,
    todo_record,
)
from planbook.client import PlanbookClient
from planbook.errors import ApiError
from planbook.resources.todos import update_todo


@responses.activate
def test_update_todo_carries_over_what_the_caller_did_not_name():
    # /updateToDo replaces the whole record, so a payload built from defaults
    # silently reopened a completed to-do and reset its priority.
    stub(
        "/getToDos",
        todo_list(
            todo_record(
                startDate="09/01/2026",
                dueDate="09/05/2026",
                priority="3",
                done="1",
                repeats="weekly",
            )
        ),
    )
    stub("/updateToDo", {"ok": True})
    # The read-back that proves the new text landed.
    stub("/getToDos", todo_list(todo_record(toDoText="New")))
    update_todo(PlanbookClient("t.t.t"), todo_id=7, text="New")
    sent = dict(
        urllib.parse.parse_qsl(
            [c for c in responses.calls if c.request.url.endswith("/updateToDo")][
                -1
            ].request.body
        )
    )
    assert sent["toDoText"] == "New"
    assert sent["dueDate"] == "09/05/2026"
    assert sent["priority"] == "3"
    assert sent["done"] == "1"
    assert sent["repeats"] == "weekly"


@responses.activate
def test_update_todo_raises_on_a_missing_id_instead_of_blanking():
    stub("/getToDos", todo_list())
    with pytest.raises(ApiError):
        update_todo(PlanbookClient("t.t.t"), todo_id=999, text="x")
