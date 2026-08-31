---
paths:
  - '**/*.py'
---

# Code style

Formatting, import order, line length and the `Any` ban are enforced by `ruff`
and `mypy`. Run them; they are the source of truth. What follows is the part a
linter cannot check.

## Types

- When mypy cannot narrow a value, add the missing check — do not widen the
  annotation. A narrowing error is usually a real missing check.
- Instead of `Any`: `JsonValue` for a parsed response body, narrowed with a
  `narrow.py` helper; a `TypedDict` from `types.py` for a known shape; `Id`,
  `FormPayload` or `Result`; `object` when genuinely unconstrained.

## Naming

- Wire keys use the server's abbreviated names (`cId`, `mT`, `lessonText`).
  Public-facing output uses readable snake_case (`class_id`, `teaches`, `text`).
- Every mapped entity gets one readable projection in `projection.py`, and `id`
  means the same thing on all of them. `--raw` is the only path that returns a
  wire record unchanged.
- Wire-format helpers live in `wire.py`; per-resource calls in `resources/`.
  A resource module that needs wire records internally exposes a `wire_*`
  reader beside its projected `list_*`.

## Error handling

- Every failure is a `PlanbookError` subclass carrying `exit_code`, `kind`,
  `retryable` and `remedy`. Add a class rather than raising a bare message.
- Exit 65 on unexpected response shapes. See `decisions/2026-08-28-fail-on-schema-drift.md`.
- API errors (`{"error":"true"}`) raise `ApiError` (exit 1).
- Auth failures return exit 77 with an actionable message.

## Writes

- Every write goes through `mutations.py`: build a `Mutation`, then `preview()`
  for `--dry-run` or `commit()` with a `verify` callback. Do not post from a
  resource module directly, and do not hand-roll a dry-run envelope.
- Bump `CONTRACT_VERSION` in `contract.py` when an output shape changes.

## Comments

- Avoid inline comments. Usually needing to add comments means the code should be rewritten to be more readable. On the rare occasions inline comments are needed they should be very short.
- Say what the code does and why. Do not describe what it used to do — that is
  what `git log` is for.
  
