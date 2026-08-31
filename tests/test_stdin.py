"""Text flags that read their value from stdin."""

import io

import responses

from conftest import (
    lesson_days,
    parse_stdout,
    stub,
)
from planbook import cli

# --- stdin bodies ----------------------------------------------------------


@responses.activate
def test_a_text_flag_reads_stdin_so_html_never_goes_through_a_shell(
    capsys, monkeypatch, session_file
):
    stub("/getLessonsEvents", lesson_days())
    monkeypatch.setattr("sys.stdin", io.StringIO("<p>Chloroplasts</p>\n"))
    monkeypatch.setattr("planbook.cli_support._STDIN_TEXT", None)
    cli.main(
        [
            "lessons",
            "set",
            "--class-id",
            "1",
            "--date",
            "09/03/2026",
            "--text",
            "-",
            "--dry-run",
        ]
    )
    body, _ = parse_stdout(capsys)
    # One trailing newline is the shell's, not part of the lesson.
    assert body["payload"]["lessonText"] == "<p>Chloroplasts</p>"


def test_two_flags_cannot_both_claim_stdin(monkeypatch, session_file):
    monkeypatch.setattr("sys.stdin", io.StringIO("x"))
    monkeypatch.setattr("planbook.cli_support._STDIN_TEXT", None)
    assert (
        cli.main(
            [
                "lessons",
                "set",
                "--class-id",
                "1",
                "--date",
                "09/03/2026",
                "--text",
                "-",
                "--notes",
                "-",
                "--dry-run",
            ]
        )
        == 64
    )


def test_a_section_cannot_claim_stdin_alongside_a_text_flag(monkeypatch, session_file):
    monkeypatch.setattr("sys.stdin", io.StringIO("x"))
    monkeypatch.setattr("planbook.cli_support._STDIN_TEXT", None)
    assert (
        cli.main(
            [
                "lessons",
                "set",
                "--class-id",
                "1",
                "--date",
                "09/03/2026",
                "--text",
                "-",
                "--section",
                "4=-",
                "--dry-run",
            ]
        )
        == 64
    )


@responses.activate
def test_a_todo_text_flag_reads_stdin(capsys, monkeypatch, session_file):
    monkeypatch.setattr("sys.stdin", io.StringIO("Grade the lab reports\n"))
    monkeypatch.setattr("planbook.cli_support._STDIN_TEXT", None)
    cli.main(
        [
            "todos",
            "create",
            "--text",
            "-",
            "--start",
            "09/03/2026",
            "--dry-run",
        ]
    )
    body, _ = parse_stdout(capsys)
    # Two requests: the create, then the write that fills it in.
    assert body["requests"][1]["payload"]["toDoText"] == "Grade the lab reports"
