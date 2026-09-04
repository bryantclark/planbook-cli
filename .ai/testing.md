---
paths:
  - '**/tests/**'
  - '**/*_test.py'
  - '**/test_*.py'
---

# Testing

## No network calls

Every test uses `responses` to mock HTTP. No test hits `api.planbook.com`,
with one deliberate exception: `test_live.py` runs a read-only `check` against a
real account when `PLANBOOK_LIVE_TOKEN` is set, and is skipped otherwise. It
exists to catch upstream schema drift before a release; CI never runs it.
`conftest.py` holds config isolation and the wire-record builders (`saved_lesson`,
`class_record`, `student_record`, `unit_record`, `todo_record`, `event_record`,
`schedule_row`) plus the `stub()` helper. Build a stub from those and pass the
field the test is about as an override, so the odd value stays visible in the
test rather than buried in a default.

## What to test

- Each CLI subcommand: verify it sends the right wire payload and maps the
  response to readable output.
- Wire format edge cases: `Y`/`N` booleans, `0` for absent integers, date
  format, repeated form fields for standards.
- `SchemaDrift` detection: verify the CLI stops on unexpected response shapes.

## Where tests live

- `tests/` at the repo root, flat. One module per resource (`test_lessons.py`,
  `test_classes.py`, ...) mirroring `src/planbook/resources/`, plus one per
  cross-cutting concern: `test_mutations.py` for the write seam, `test_cli.py`
  for the process contract, `test_wire.py` for parsing, `test_client.py` for HTTP.
