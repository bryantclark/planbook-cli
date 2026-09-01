# planbook-cli

Unofficial CLI for [Planbook.com](https://planbook.com). Reads and writes lesson
plans, schedules, grades, and attendance — built for people and AI agents.

Not affiliated with or supported by Planbook.com. It works on your own account
with your own credentials. See [SECURITY.md](SECURITY.md) for what it does with
them and [docs/PRODUCTION-READINESS.md](docs/PRODUCTION-READINESS.md) for what
an official version would take.

No published API exists; this tool talks to the same endpoints the web app uses.
See [docs/API-NOTES.md](docs/API-NOTES.md) for details.
Run `planbook endpoints` for current coverage.

## Install

```bash
pipx install planbook-cli
```

```bash
uv tool install planbook-cli
```

To update: `pipx upgrade planbook-cli` or `uv tool upgrade planbook-cli`.

Unreleased `main`: `pipx install git+https://github.com/bryantclark/planbook-cli`.

Development: clone, then `uv pip install -e ".[dev]"`.

## Quickstart

```bash
planbook auth import            # read the token from your browser
planbook check                  # session, hours left, and your class ids
planbook lessons set --class-id 12345678 --date 09/03/2026 \
  --title "Photosynthesis" --text "<p>Chloroplasts and light reactions.</p>"
```

## For agents

The CLI describes itself, so nothing has to be inferred from help text or
guessed from prose:

```bash
planbook schema                 # every command, flag and error kind as JSON
planbook check                  # the one-call preflight
planbook --error-json <cmd>     # failures as {"error": {kind, code, retryable, remedy}}
```

- stdout is JSON on success and empty on failure. Branch on the exit code.
- `-` on any text flag reads that value from stdin, so HTML never goes through
  a shell.
- Every list answers to `id`; `--raw` returns the untouched wire body.
- Every write has `--dry-run`, and is read back before it reports success.
- Deletes that destroy records you did not name require `--yes` and report a
  `cascade` count. So does `raw` on anything but `--get`, since an unmapped
  POST can reach a deleting endpoint.
- `lessons bulk --journal FILE` makes an interrupted batch resumable with
  `--resume`.

[AGENTS.md](AGENTS.md) is the full contract.

## Authentication

- **`auth import`** (recommended) — reads the token from a browser you are already signed in to. On macOS, approve the Keychain prompt (**Always Allow**).
- **`auth token`** — paste a bare JWT, `Cookie:` header, or "Copy as cURL" output. The fallback when the cookie store can't be read (Safari without Full Disk Access).

Both paths carry a full-account token with no scopes, consent, or revocation.
See [docs/PRODUCTION-READINESS.md](docs/PRODUCTION-READINESS.md) for what should
replace them.

Token storage: `~/.config/planbook/token.json` (mode 0600). `PLANBOOK_TOKEN` overrides for CI.

**Tokens last about 22 hours (1 hour for auth-server tokens).** Re-run `auth import` daily.

### Getting your token by hand

1. Sign in to Planbook, open DevTools **Network** tab, filter `api.planbook.com`.
2. Reload, click the `getClasses2` request.
3. Right-click > **Copy** > **Copy as cURL**.
4. Run `planbook auth token` and paste.

## Caveats

- No published API exists; endpoints can change. See [docs/API-NOTES.md](docs/API-NOTES.md).
- Only `api.planbook.com` is used; the web app host is never scripted.
- Requests are serialized. No parallelism.
- Planbook's terms (2020-07-01) have no anti-automation clause but reserve rate limits and allow discretionary termination.
- There's evidence of a sanctioned API-key mechanism. If you depend on this tool, ask support@planbook.com about it.

## Agent discovery

Install the skill so Claude finds the CLI automatically:

```bash
mkdir -p ~/.claude/skills/planbook && cp skills/planbook/SKILL.md AGENTS.md docs/API-NOTES.md ~/.claude/skills/planbook/
```

`SKILL.md` carries the contract on its own; the other two are the full reference
it points at. Or install the repo as a [plugin](.claude-plugin/plugin.json).

## Licence

MIT.

## Releasing (maintainer)

Release-please gathers `main` merges into a version-bump PR. Merge it to tag and
publish to PyPI.

`feat:` bumps minor, `fix:` bumps patch. Squash-merge PRs with a conventional
title. To force a specific version, put `Release-As: X.Y.Z` on its own line in
the squash commit body.

The release PR is opened by the Actions bot. GitHub doesn't run CI on bot-opened
PRs, so close and reopen it once (`gh pr close N && gh pr reopen N`). To skip this
permanently, give release-please a fine-grained PAT.

First publish: create `planbook-cli` on PyPI, add a trusted publisher (workflow
`publish.yml`, environment `pypi`), add a GitHub environment named `pypi`.
