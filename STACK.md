---
type: python-pkg
package_manager: uv
test_runner: pytest
db: none
deploy: pypi
language: python
---

# Stack

## Why these choices

Python for the audience (teachers and agents, not systems engineers). `requests`
over `httpx` because every call is serial by design — async adds nothing. `browser-cookie3`
reads browser cookie stores so `auth import` needs no manual paste. `hatchling` builds the wheel;
`ruff` formats and lints; `mypy --strict` type-checks.

## Common commands

- **Dev install**: `uv pip install -e ".[dev]"`
- **Test**: `pytest` — `pyproject.toml` puts `src` on the path, so this always
  tests the checked-out source rather than whichever `planbook` is installed
- **Contract test**: `PLANBOOK_LIVE=1 pytest tests/live/test_contract.py` — the
  opt-in read-only pass against the real account, skipped by default
- **HTML round trip**: `PLANBOOK_LIVE_WRITE=1 pytest
  tests/live/test_html_roundtrip.py -s` — creates its own class, writes
  lessons in it, deletes the class afterwards
- **Lint**: `ruff check src tests`
- **Format**: `ruff format src tests`
- **Type check**: `mypy` (reads `pyproject.toml`)
- **Run**: `planbook --help`
