"""What Planbook does to lesson text it stores. Opt-in, and it writes.

`same()` in fields.py compares stored text to written text byte for byte, so
if the server rewraps a bare string or re-encodes an entity, `lessons set
--text` raises PostconditionFailed on a write that landed. Carry-over then
resends the server's own copy on the next write, which is how a rewrite
compounds across edits. Neither is confirmed. This confirms or clears it.

It writes real lessons, so it needs more than `PLANBOOK_LIVE`:

    PLANBOOK_LIVE_WRITE=1 \\
    PLANBOOK_TEST_CLASS_ID=12345678 \\
    PLANBOOK_TEST_DATE=09/03/2026 \\
    pytest tests/live/test_html_roundtrip.py -s

Use a throwaway class. The date must hold no lesson: the run refuses to start
otherwise, rather than overwriting one. It writes one lesson, rewrites it once
per shape, and deletes it at the end.

`-s` prints the shape-by-shape table, which is the actual output. Paste it into
docs/API-NOTES.md.
"""

from __future__ import annotations

import os

import pytest

from planbook import config
from planbook.client import PlanbookClient
from planbook.errors import PostconditionFailed
from planbook.resources.lessons import delete_lesson, find_lesson, set_lesson

LIVE = os.environ.get("PLANBOOK_LIVE_WRITE") == "1"
CLASS_ID = os.environ.get("PLANBOOK_TEST_CLASS_ID")
DATE = os.environ.get("PLANBOOK_TEST_DATE")

# Read at import, before conftest's isolated_config rewrites HOME.
TOKEN = config.load_session_or_none() if LIVE else None

pytestmark = pytest.mark.skipif(
    not LIVE,
    reason="set PLANBOOK_LIVE_WRITE=1 with PLANBOOK_TEST_CLASS_ID and "
    "PLANBOOK_TEST_DATE to run; it writes real lessons",
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
    "empty": "",
    "long body": "<p>" + ("word " * 2000).strip() + "</p>",
}


@pytest.fixture(scope="module")
def client() -> PlanbookClient:
    if not TOKEN:
        pytest.fail("No stored session. Run `planbook auth import` first.")
    if not CLASS_ID or not DATE:
        pytest.fail("Set PLANBOOK_TEST_CLASS_ID and PLANBOOK_TEST_DATE.")
    return PlanbookClient(TOKEN)


@pytest.fixture(scope="module")
def lesson_slot(client: PlanbookClient):
    """An empty class/date, given back empty.

    Refusing a slot that already holds a lesson is the safety property: this
    test overwrites its slot ten times.
    """
    if find_lesson(client, class_id=CLASS_ID, date=DATE) is not None:
        pytest.fail(
            f"class {CLASS_ID} already has a lesson on {DATE}. "
            "Point this at an empty date in a throwaway class."
        )
    yield CLASS_ID, DATE
    delete_lesson(client, class_id=CLASS_ID, date=DATE)


def stored_text(client: PlanbookClient) -> str:
    record = find_lesson(client, class_id=CLASS_ID, date=DATE)
    assert record is not None, "the lesson vanished between write and read"
    value = record.get("lessonText")
    return "" if value is None else str(value)


def write(client: PlanbookClient, text: str) -> tuple[str, bool]:
    """Write one shape and read it back. Returns the stored text and whether
    the CLI's own postcondition accepted it."""
    try:
        set_lesson(client, class_id=CLASS_ID, date=DATE, title="round trip", text=text)
    except PostconditionFailed:
        return stored_text(client), False
    return stored_text(client), True


def test_lesson_text_survives_a_round_trip(client, lesson_slot, capsys):
    rows = []
    rewritten = []
    unstable = []
    rejected = []

    for name, text in SHAPES.items():
        stored, accepted = write(client, text)
        # The second pass sends what the server itself returned. A shape that
        # changes again is one that compounds every time a lesson is edited.
        again, _ = write(client, stored)

        if not accepted:
            rejected.append(name)
        if stored != text:
            rewritten.append(name)
        if again != stored:
            unstable.append(name)
        rows.append((name, text, stored, again))

    with capsys.disabled():
        print("\n\n| shape | verdict | sent | stored |")
        print("|---|---|---|---|")
        for name, text, stored, again in rows:
            verdict = (
                "unstable"
                if again != stored
                else "rewritten"
                if stored != text
                else "verbatim"
            )
            print(f"| {name} | {verdict} | `{_cell(text)}` | `{_cell(stored)}` |")
        print()

    assert not unstable, (
        f"{unstable} change again when the stored text is resent, so carry-over "
        "compounds the rewrite on every edit. Normalise before comparing and "
        "before resending."
    )
    assert not rejected, (
        f"{rejected} raised PostconditionFailed on a write that landed. "
        f"`same()` needs to normalise these before comparing (see fields.py). "
        f"Server rewrote: {rewritten}."
    )


def _cell(value: str, limit: int = 60) -> str:
    flat = value.replace("|", "\\|").replace("\n", " ")
    return flat if len(flat) <= limit else flat[:limit] + "..."
