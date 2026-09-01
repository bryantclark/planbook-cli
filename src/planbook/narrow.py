"""Narrowing helpers for parsed JSON.

`PlanbookClient` returns `JsonValue`, so nothing can be indexed before it is
checked. Each helper either narrows the type or raises `SchemaDrift`.
"""

from __future__ import annotations

from .errors import SchemaDrift
from .types import Id, JsonObject, JsonRecord, JsonValue


def as_object(value: JsonValue, *, where: str) -> JsonObject:
    """The body as an object, or stop."""
    if not isinstance(value, dict):
        raise SchemaDrift(
            f"{where}: expected an object, got {_name(value)}. "
            "The API shape may have changed."
        )
    return value


def as_list(value: JsonValue, *, where: str) -> list[JsonValue]:
    """The body as a list, or stop."""
    if not isinstance(value, list):
        raise SchemaDrift(
            f"{where}: expected a list, got {_name(value)}. "
            "The API shape may have changed."
        )
    return value


def records(value: JsonValue, *, where: str) -> list[JsonObject]:
    """The objects in a wire array, or stop.

    A row that is not an object is drift, not noise: dropping it returned a
    short list that read as "the account has fewer of these".
    """
    rows = as_list(value, where=where)
    bad = [i for i, item in enumerate(rows) if not isinstance(item, dict)]
    if bad:
        raise SchemaDrift(
            f"{where}: row(s) {bad} are not objects. The API shape may have changed."
        )
    return [item for item in rows if isinstance(item, dict)]


def unwrap(
    value: JsonValue, key: str, *, where: str, required: bool = True
) -> list[JsonObject]:
    """The records under `key` in an envelope like `{"units": [...]}`.

    `required=False` also accepts a bare array: some endpoints answer either
    way depending on the account.
    """
    if not required and not isinstance(value, dict):
        return records(value, where=where)
    body = as_object(value, where=where)
    if key not in body:
        if not required:
            return records(body, where=where)
        raise SchemaDrift(
            f"{where}: response is missing {key}. The API shape may have changed."
        )
    return records(body[key], where=f"{where}.{key}")


def as_id(value: object, *, where: str) -> Id:
    """A record id, or stop. `bool` is excluded despite subclassing `int`."""
    if isinstance(value, bool) or not isinstance(value, int | str):
        raise SchemaDrift(
            f"{where}: expected a record id, got {_name(value)}. "
            "The API shape may have changed."
        )
    return value


def text(record: JsonRecord, *keys: str) -> str | None:
    """The first of `keys` that carries something, as a string."""
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def string(record: JsonRecord, key: str, default: str = "") -> str:
    """One field as a string, with a default when it is absent or empty."""
    value = record.get(key)
    return default if value in (None, "") else str(value)


def flag(value: object) -> bool:
    """Planbook booleans arrive as bools, "Y"/"N", "true"/"false" or "1"/"0"."""
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("y", "yes", "true", "1")


def _name(value: object) -> str:
    return type(value).__name__
