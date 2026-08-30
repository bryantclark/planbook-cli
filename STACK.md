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

Python because the audience is teachers and agents, not systems engineers. `requests`
over `httpx` because every call is serial by design — async adds nothing. `browser-cookie3`
reads browser cookie stores for zero-copy auth import. `hatchling` builds the wheel;
`ruff` formats and lints; `mypy --strict` type-checks.

Optional `playwright` dependency powers `auth browser` (headed sign-in). Not installed
by default because most users authenticate through `auth import`.

## Common commands

- **Dev install**: `uv pip install -e ".[dev]"`
- **Test**: `pytest`
- **Lint**: `ruff check src tests`
- **Format**: `ruff format src tests`
- **Type check**: `mypy` (reads `pyproject.toml`)
- **Run**: `planbook --help`
