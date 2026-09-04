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
- **Live smoke test** (read-only, before a release):
  `PLANBOOK_LIVE_TOKEN=$(jq -r .token ~/.config/planbook/token.json) pytest tests/test_live.py`
- **Lint**: `ruff check src tests`
- **Format**: `ruff format src tests`
- **Type check**: `mypy` (reads `pyproject.toml`)
- **Run**: `planbook --help`
