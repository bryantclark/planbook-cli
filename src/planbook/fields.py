"""Declarative field tables for the read-modify-write path.

Planbook's write endpoints replace the whole record, so every update is a
read-modify-write: read the current values, overwrite the ones the caller
named, resend all of them. Only the named ones can be verified - comparing a
carried-over value against itself passes whether or not the server stored
anything.

Both halves come from one table. A resource declares its fields once and gets
the carry-over and the postcondition from the same declaration, so a field
cannot be written without being checked.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from html import unescape

from .narrow import flag
from .types import JsonRecord


@dataclass(frozen=True)
class Field:
    """One field of a record, in both the endpoint's vocabularies.

    `write` is the form key the write accepts; `reads` are the keys the read
    answers with, which are not always the same and vary by account. `carry`
    converts a stored value to what the write wants, for a field the two sides
    spell differently.
    """

    public: str
    write: str
    reads: Sequence[str] = ()
    is_flag: bool = False
    default: str = ""
    carry: Callable[[object], str] | None = None

    @property
    def read_keys(self) -> tuple[str, ...]:
        return tuple(self.reads) or (self.write,)

    def carried(self, existing: JsonRecord) -> str:
        """This field's current value, from whichever key the read used."""
        for key in self.read_keys:
            stored = existing.get(key)
            if stored not in (None, ""):
                if self.is_flag:
                    return "1" if flag(stored) else "0"
                return self.carry(stored) if self.carry else str(stored)
        return "0" if self.is_flag else self.default


@dataclass
class Edit:
    """A resolved read-modify-write: what to send, and what to check."""

    #: Public name -> the value to send, whether named or carried over.
    values: dict[str, str] = field(default_factory=dict)
    named: dict[str, tuple[str, str]] = field(default_factory=dict)
    checks: dict[str, Callable[[JsonRecord], bool]] = field(default_factory=dict)
    flags: frozenset[str] = frozenset()

    def __getitem__(self, public: str) -> str:
        return self.values[public]

    def set(self, public: str, value: str) -> None:
        """Change a resolved value, keeping its postcondition in step.

        For a value the payload derives rather than sends as given - a due date
        defaulting to the start date - so the read-back checks what was sent.
        """
        self.values[public] = value
        if public in self.named:
            self.named[public] = (self.named[public][0], value)


def resolve(
    table: Sequence[Field],
    existing: JsonRecord,
    given: Mapping[str, str | bool | None],
) -> Edit:
    """Fill the payload from `given`, falling back to the saved record.

    `None` means the caller did not name the field, so it is carried over.
    `""` means they cleared it - a real edit, and checked like any other.
    """
    edit = Edit()
    flags: set[str] = set()
    for spec in table:
        value = given.get(spec.public)
        if value is None:
            edit.values[spec.public] = spec.carried(existing)
            continue
        written = _written(spec, value)
        edit.values[spec.public] = written
        if spec.is_flag:
            flags.add(spec.public)
        if len(spec.read_keys) == 1:
            edit.named[spec.public] = (spec.read_keys[0], written)
        else:
            edit.checks[spec.public] = _alias_check(spec, written)
    edit.flags = frozenset(flags)
    return edit


def _written(spec: Field, value: str | bool) -> str:
    if spec.is_flag:
        return "1" if flag(value) else "0"
    return str(value)


def _alias_check(spec: Field, written: str) -> Callable[[JsonRecord], bool]:
    """Compare only the aliases the read-back actually carries.

    Which key a read answers with varies by account, so it is only knowable
    from the read-back itself. A sibling alias is always absent - the endpoint
    answers under one convention - so accepting any absent key would pass a
    clear (`""`) vacuously, whatever the server kept.
    """

    def check(record: JsonRecord) -> bool:
        present = [key for key in spec.read_keys if key in record]
        if not present:
            return written == ""
        return all(
            same(record.get(key), written, is_flag=spec.is_flag) for key in present
        )

    return check


def same(stored: object, written: str, *, is_flag: bool = False) -> bool:
    """Whether a read-back value is what was written.

    An absent field reads as empty, not as the string "None": a write that
    legitimately stores nothing must not look like a failure. A flag compares
    as a boolean, because Planbook answers one as a bool, "Y"/"N",
    "true"/"false" or "1"/"0". Which fields those are is declared by the
    resource, not guessed from the value: a field set to "0" is not a flag.

    Values compare with surrounding whitespace stripped, and with HTML
    entities resolved. Planbook re-encodes what it stores: a bare `&` comes
    back `&amp;`, and `-`, `"` and their unicode cousins come back `&mdash;`,
    `&ldquo;` and friends. Comparing those byte for byte failed a write that
    had landed. The rewrite is idempotent - storing the stored text returns it
    unchanged - so carry-over resends it safely. See docs/API-NOTES.md.
    """
    if is_flag:
        return flag(stored) is flag(written)
    if stored is None:
        return written.strip() == ""
    return _plain(stored) == _plain(written)


def _plain(value: object) -> str:
    """One side of a comparison, with entities resolved and edges trimmed."""
    return unescape(str(value)).strip()
