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

Two modules are exceptions. `tests/test_contract_live.py` reads the real
account to check the projections still match the API. It skips unless
`PLANBOOK_LIVE=1`, so the default run stays offline, and it never writes. Add a
case there when you map a reader; keep writes out of it.

`tests/test_html_roundtrip_live.py` measures what Planbook does to text it
stores. It writes, so it needs `PLANBOOK_LIVE_WRITE=1` plus a class id and a
date, refuses a date that already holds a lesson, and deletes what it made.
Run it against a throwaway class, never a real one.

## What to test

- Each CLI subcommand: verify it sends the right wire payload and maps the
  response to readable output.
- Wire format edge cases: `Y`/`N` booleans, `0` for absent integers, date
  format, repeated form fields for standards.
- `SchemaDrift` detection: verify the CLI stops on unexpected response shapes.

## Where tests live

- `tests/` at the repo root, flat: one module per area (`test_api.py`, `test_cli.py`).
