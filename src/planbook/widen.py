"""Widening helpers: values on their way out, not in.

`list` and `dict` are invariant, so a `list[str]` cannot sit in a `JsonValue`
slot even though every element fits. These rebuild rather than cast.
"""

from __future__ import annotations

from collections.abc import Sequence

from .types import FormBody, JsonObject, JsonValue


def json_of(payload: FormBody) -> JsonObject:
    body: JsonObject = {}
    for key, value in payload.items():
        if isinstance(value, list):
            items: list[JsonValue] = list(value)
            body[key] = items
        else:
            body[key] = value
    return body


def json_list(values: Sequence[str]) -> list[JsonValue]:
    """A list of strings, widened so it can sit in a JSON body."""
    return list(values)
