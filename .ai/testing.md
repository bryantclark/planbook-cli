---
paths:
  - '**/tests/**'
  - '**/*_test.py'
  - '**/test_*.py'
---

# Testing

## No network calls

Every test uses `responses` to mock HTTP. No test hits `api.planbook.com`.
`conftest.py` holds config isolation and the wire-record builders (`saved_lesson`,
`class_record`, `student_record`, `unit_record`, `todo_record`, `event_record`,
`schedule_row`) plus the `stub()` helper. Build a stub from those and pass the
field the test is about as an override, so the odd value stays visible in the
test rather than buried in a default.

`tests/live/` is the exception, and everything in it is skipped by default.
`tests/live/test_contract.py` reads the real account to check the projections
still match the API. It skips unless `PLANBOOK_LIVE=1`, so the default run
stays offline, and it never writes. Add a case there when you map a reader;
keep writes out of it.

`tests/live/test_html_roundtrip.py` measures what Planbook does to text it
stores. It writes, so it needs `PLANBOOK_LIVE_WRITE=1`. It touches nothing that
was already there: it creates its own class, writes in that, and deletes the
class at the end. A write test added here does the same — never write into a
class the account already had.

## What to test

- Each CLI subcommand: verify it sends the right wire payload and maps the
  response to readable output.
- Wire format edge cases: `Y`/`N` booleans, `0` for absent integers, date
  format, repeated form fields for standards.
- `SchemaDrift` detection: verify the CLI stops on unexpected response shapes.

## Where tests live

- `tests/` at the repo root, flat: one module per area (`test_api.py`, `test_cli.py`).
- `tests/live/` for anything that talks to the real API. Nothing there runs
  without its environment variable.
