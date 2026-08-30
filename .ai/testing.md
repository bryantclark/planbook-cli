---
paths:
  - '**/tests/**'
  - '**/*_test.py'
  - '**/test_*.py'
---

# Testing

## No network calls

Every test uses `responses` to mock HTTP. No test hits `api.planbook.com`.
Response fixtures are inline in the test modules (`conftest.py` and `test_*.py`).

## What to test

- Each CLI subcommand: verify it sends the right wire payload and maps the
  response to readable output.
- Wire format edge cases: `Y`/`N` booleans, `0` for absent integers, date
  format, repeated form fields for standards.
- `SchemaDrift` detection: verify the CLI stops on unexpected response shapes.

## Where tests live

- `tests/` at the repo root, mirroring `src/planbook/` structure.
