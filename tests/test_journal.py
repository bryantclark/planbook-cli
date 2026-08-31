"""The bulk journal and --resume."""

import json

import pytest
import responses

from conftest import (
    event_list,
    lesson_days,
    parse_stdout,
    saved_lesson,
    stub,
)
from planbook import cli
from planbook.journal import Journal, key_for, payload_hash

# --- the bulk journal ------------------------------------------------------


def test_the_journal_only_skips_an_item_whose_content_is_unchanged(tmp_path):
    journal = Journal(tmp_path / "run.jsonl")
    key, digest = key_for(1, "09/03/2026"), payload_hash({"lessonTitle": "One"})
    journal.record({"key": key, "payload_sha256": digest, "status": "written"})
    journal.load()
    assert journal.already_written(key, digest)
    assert not journal.already_written(key, payload_hash({"lessonTitle": "Two"}))


def test_a_failed_item_is_not_treated_as_written(tmp_path):
    journal = Journal(tmp_path / "run.jsonl")
    key, digest = key_for(1, "09/03/2026"), payload_hash({"a": 1})
    journal.record({"key": key, "payload_sha256": digest, "status": "failed"})
    journal.load()
    assert not journal.already_written(key, digest)


def test_a_torn_line_from_a_killed_run_does_not_break_the_resume(tmp_path):
    path = tmp_path / "run.jsonl"
    key, digest = key_for(1, "09/03/2026"), payload_hash({"a": 1})
    path.write_text(
        json.dumps({"key": key, "payload_sha256": digest, "status": "written"})
        + '\n{"key": "1|09/04/2026", "stat'
    )
    journal = Journal(path)
    journal.load()
    assert journal.already_written(key, digest)


def test_resume_without_a_journal_is_a_usage_error(isolated_config, tmp_path):
    path = tmp_path / "lessons.json"
    path.write_text("[]")
    assert cli.main(["lessons", "bulk", str(path), "--resume"]) == 64


@responses.activate
def test_bulk_resume_skips_what_the_interrupted_run_already_wrote(
    tmp_path, capsys, session_file
):
    lessons = tmp_path / "lessons.json"
    lessons.write_text(
        json.dumps(
            [
                {"class_id": 1, "date": "09/03/2026", "title": "One"},
                {"class_id": 1, "date": "09/04/2026", "title": "Two"},
            ]
        )
    )
    journal_path = tmp_path / "run.jsonl"

    def stub_planbook(written_date, written_title):
        stub("/getEvents", event_list())
        stub("/getLessonsEvents", lesson_days())
        stub("/updateLesson", {"ok": True})
        stub(
            "/getLessonsEvents",
            saved_lesson(date=written_date, lessonTitle=written_title),
        )
        # The second item fails, so the run stops with only the first recorded.
        stub("/updateLesson", {"error": "true", "msg": "nope"})

    stub_planbook("09/03/2026", "One")
    with pytest.raises(SystemExit):
        cli.main(["lessons", "bulk", str(lessons), "--journal", str(journal_path)])
    first, _ = parse_stdout(capsys)
    assert first["written"] == 1 and first["failed"] == 1

    responses.reset()
    stub_planbook("09/04/2026", "Two")
    cli.main(
        ["lessons", "bulk", str(lessons), "--journal", str(journal_path), "--resume"]
    )
    second, _ = parse_stdout(capsys)
    assert second["skipped"] == 1
    assert second["written"] == 1
    # Only the item that had not landed was sent again.
    writes = [c for c in responses.calls if c.request.url.endswith("/updateLesson")]
    assert len(writes) == 1
