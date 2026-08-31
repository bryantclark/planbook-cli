"""Readable-key projections: one `id` per record, and the raw wire
body left untouched where a command offers it.
"""

import pytest
import responses

from conftest import (
    stub,
    todo_list,
    todo_record,
    unit_list,
    unit_record,
)
from planbook import projection
from planbook.client import PlanbookClient
from planbook.errors import (
    SchemaDrift,
)
from planbook.resources.todos import list_todos, raw_todos
from planbook.resources.units import (
    list_units,
    raw_units,
)

# --- projections -----------------------------------------------------------


def test_units_todos_and_events_all_answer_to_id():
    assert projection.unit({"unitId": 4, "unitTitle": "U"})["id"] == 4
    assert projection.todo({"toDoId": 7, "toDoText": "t"})["id"] == 7
    assert projection.event({"eventId": 9, "eventTitle": "E"})["id"] == 9


def test_a_projection_carries_no_wire_id_key():
    # One id per record. A second spelling is one more thing to memorise.
    assert "unitId" not in projection.unit({"unitId": 4})
    assert "toDoId" not in projection.todo({"toDoId": 7})
    assert "eventId" not in projection.event({"eventId": 9})


def test_todo_priority_and_done_come_back_readable():
    record = projection.todo({"toDoId": 1, "priority": "3", "done": "1"})
    assert record["priority"] == "high"
    assert record["done"] is True


def test_projection_rejects_a_record_that_is_not_an_object():
    with pytest.raises(SchemaDrift):
        projection.unit(["not", "an", "object"])


@responses.activate
def test_units_list_projects_and_raw_does_not():
    wire = unit_list(unit_record(unitId=4, unitTitle="Cells"))
    stub("/getUnits", wire)
    stub("/getUnits", wire)
    client = PlanbookClient("t.t.t")
    assert list_units(client)[0]["title"] == "Cells"
    assert raw_units(client) == wire


@responses.activate
def test_todos_list_projects_and_raw_does_not():
    wire = todo_list(todo_record(toDoId=2, toDoText="Grade", priority="2"))
    stub("/getToDos", wire)
    stub("/getToDos", wire)
    client = PlanbookClient("t.t.t")
    assert list_todos(client)[0]["priority"] == "medium"
    assert raw_todos(client) == wire
