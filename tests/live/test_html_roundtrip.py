"""What Planbook does to lesson text it stores. Opt-in, and it writes.

`same()` in fields.py compares stored text to written text byte for byte, so
if the server rewraps a bare string or re-encodes an entity, `lessons set
--text` raises PostconditionFailed on a write that landed. Carry-over then
resends the server's own copy on the next write, which is how a rewrite
compounds across edits. Neither is confirmed. This confirms or clears it.

It writes, so it is gated on its own variable:

    PLANBOOK_LIVE_WRITE=1 pytest tests/live/test_html_roundtrip.py -s

It touches nothing that was already there. It creates its own class, writes one
lesson in it, and deletes the class - and everything in it - at the end. If the
teardown cannot delete, it says so loudly and names the id: that class is the
only trace this test can leave.

`-s` prints the shape-by-shape table, which is the actual output. Paste it into
docs/API-NOTES.md.
"""

from __future__ import annotations

import datetime
import os
from collections.abc import Iterator

import pytest

from planbook import config
from planbook.client import PlanbookClient
from planbook.errors import PlanbookError, PostconditionFailed
from planbook.resources.classes import create_class, delete_class
from planbook.resources.lessons import find_lesson, set_lesson

LIVE = os.environ.get("PLANBOOK_LIVE_WRITE") == "1"

# Read at import, before conftest's isolated_config rewrites HOME.
TOKEN = config.load_session_or_none() if LIVE else None

pytestmark = pytest.mark.skipif(
    not LIVE,
    reason="set PLANBOOK_LIVE_WRITE=1 to run; it creates a class and writes "
    "lessons in the signed-in account",
)

#: The shapes an agent actually sends, plus the ones most likely to be rewritten.
SHAPES = {
    "plain text": "Read chapter 4.",
    "one paragraph": "<p>Read chapter 4.</p>",
    "two paragraphs": "<p>First.</p><p>Second.</p>",
    "nested list": "<ul><li>One<ul><li>Inner</li></ul></li></ul>",
    "named entity": "<p>Salt &amp; pepper</p>",
    "bare ampersand": "<p>Salt & pepper</p>",
    "unicode": "<p>Caf\u00e9 \u2014 na\u00efve \u2013 \u201cquoted\u201d</p>",
    "script tag": "<p>ok</p><script>alert(1)</script>",
    "trailing space": "<p>Read chapter 4.</p> ",
    "empty": "",
    "long body": "<p>" + ("word " * 2000).strip() + "</p>",
}

#: The three text sections every layout has. A rewrite could be per-field.
SECTIONS = ("text", "homework", "notes")
STORED_KEYS = {"text": "lessonText", "homework": "homeworkText", "notes": "notesText"}


@pytest.fixture(scope="module")
def client() -> PlanbookClient:
    if not TOKEN:
        pytest.fail("No stored session. Run `planbook auth import` first.")
    return PlanbookClient(TOKEN)


@pytest.fixture(scope="module")
def slot(client: PlanbookClient) -> Iterator[tuple[object, str]]:
    """A class of this test's own, and a date it teaches. Deleted afterwards.

    Creating one is what keeps this off a real class: nothing it writes can
    land on a lesson somebody wanted, and the cleanup is one delete rather
    than a list of things to undo.
    """
    monday = _next_monday()
    end = monday + datetime.timedelta(days=28)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    created = create_class(
        client,
        name=f"planbook-cli round trip {stamp}",
        start_date=monday.strftime("%m/%d/%Y"),
        end_date=end.strftime("%m/%d/%Y"),
        days=["M"],
        description="Created by tests/live/test_html_roundtrip.py. Safe to delete.",
    )
    class_id = created["id"]
    try:
        yield class_id, monday.strftime("%m/%d/%Y")
    finally:
        try:
            delete_class(client, class_id=class_id, confirmed=True)
        except PlanbookError as exc:
            pytest.fail(
                f"could not delete the scratch class {class_id}: {exc}. "
                f"Delete it by hand: planbook classes delete --class-id "
                f"{class_id} --yes",
                pytrace=False,
            )


def _next_monday() -> datetime.date:
    today = datetime.date.today()
    return today + datetime.timedelta(days=(7 - today.weekday()) % 7 or 7)


def stored(client: PlanbookClient, class_id: object, date: str) -> dict[str, str]:
    record = find_lesson(client, class_id=class_id, date=date)
    assert record is not None, "the lesson vanished between write and read"
    return {
        name: "" if record.get(key) is None else str(record[key])
        for name, key in STORED_KEYS.items()
    }


def write(
    client: PlanbookClient, class_id: object, date: str, value: dict[str, str]
) -> tuple[dict[str, str], bool]:
    """Write one shape into all three sections and read them back.

    Returns what came back and whether the CLI's own postcondition accepted
    it. A `PostconditionFailed` here is the finding, not a broken test: the
    write landed and the read-back disagreed with it.
    """
    try:
        set_lesson(
            client,
            class_id=class_id,
            date=date,
            title="round trip",
            text=value["text"],
            homework=value["homework"],
            notes=value["notes"],
        )
    except PostconditionFailed:
        return stored(client, class_id, date), False
    return stored(client, class_id, date), True


def test_lesson_text_survives_a_round_trip(client, slot, capsys):
    class_id, date = slot
    rows = []
    rejected: list[str] = []
    unstable: list[str] = []
    per_field: list[str] = []

    for name, text in SHAPES.items():
        sent = dict.fromkeys(SECTIONS, text)
        back, accepted = write(client, class_id, date, sent)
        # Resending what the server itself returned is what separates a one-off
        # rewrite from one that compounds on every later edit.
        again, _ = write(client, class_id, date, back)

        if not accepted:
            rejected.append(name)
        if again != back:
            unstable.append(name)
        if len(set(back.values())) > 1:
            per_field.append(name)
        rows.append((name, text, back, again))

    with capsys.disabled():
        print("\n\n| shape | verdict | sent | stored as `text` |")
        print("|---|---|---|---|")
        for name, text, back, again in rows:
            print(
                f"| {name} | {_verdict(text, back, again)} "
                f"| `{_cell(text)}` | `{_cell(back['text'])}` |"
            )
        if per_field:
            print(f"\nStored differently per section: {per_field}")
        print()

    assert not unstable, (
        f"{unstable} change again when the stored text is resent, so the "
        "rewrite compounds every time a lesson is edited. Normalise in "
        "`carried()` before resending, not only in `same()`."
    )
    assert not rejected, (
        f"{rejected} raised PostconditionFailed on a write that landed. "
        "`same()` in fields.py compares byte for byte; it needs to normalise "
        "these first."
    )


def _verdict(text: str, back: dict[str, str], again: dict[str, str]) -> str:
    if again != back:
        return "unstable"
    if any(v != text for v in back.values()):
        return "rewritten"
    return "verbatim"


def _cell(value: str, limit: int = 60) -> str:
    flat = value.replace("|", "\\|").replace("\n", " ")
    return flat if len(flat) <= limit else flat[:limit] + "..."
