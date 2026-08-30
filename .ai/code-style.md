---
paths:
  - '**/*.py'
---

# Code style

## Type safety

- `mypy --strict` must pass. No `type: ignore` without an error code.
- No `Any` except at the JSON-parsing boundary (wire responses). Narrow immediately after.

## Naming

- Wire keys use the server's abbreviated names (`cId`, `mT`, `lessonText`).
  Public-facing output uses readable snake_case (`class_id`, `teaches`, `text`).
- Translation between wire and readable happens in `resources/` or `api.py`, nowhere else.

## Error handling

- Exit 65 on unexpected response shapes. See `decisions/2026-08-28-fail-on-schema-drift.md`.
- API errors (`{"error":"true"}`) raise `ApiError` (exit 1).
- Auth failures return exit 77 with an actionable message.

## Imports

- Standard library, then third-party, then project. `ruff` enforces ordering.
- Every module has `from __future__ import annotations`. Keep it.

## Formatting

- `ruff format` with the settings in `pyproject.toml`. Line length 88.
