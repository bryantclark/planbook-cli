# planbook-cli

Unofficial CLI for [Planbook.com](https://planbook.com). Reads and writes lesson
plans through the private API that the web app uses.

Built against the web app's API — no published API exists yet. See
[docs/API-NOTES.md](docs/API-NOTES.md) for endpoint details and
[docs/RECON.md](docs/RECON.md) for how to map more.
[AGENTS.md](AGENTS.md) is the agent-facing command reference.

## Status

Run `planbook endpoints` for coverage.

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

## Agent discovery

Install the skill so agents find the CLI without being told:

```bash
mkdir -p ~/.claude/skills/planbook
cp skills/planbook/SKILL.md ~/.claude/skills/planbook/
```

Or install the repo as a plugin (`.claude-plugin/plugin.json`).

## Quickstart

```bash
planbook auth import            # read the token from your browser
planbook classes list
planbook lessons set --class-id 12345678 --date 09/03/2026 \
  --title "Photosynthesis" --text "<p>Chloroplasts and light reactions.</p>"
```

## Authentication

- **`auth import`** (recommended) — reads the cookie from your browser. On macOS, approve the Keychain prompt (**Always Allow**).
- **`auth token`** — paste a bare JWT, `Cookie:` header, or "Copy as cURL" output.
- **`auth login`** — username/password for Planbook-native accounts.
- **`auth browser`** — not recommended; identity providers refuse automated browsers.

Token storage: `~/.config/planbook/token.json` (mode 0600). `PLANBOOK_TOKEN` overrides for CI.

**Tokens last about 22 hours (1 hour for auth-server tokens).** Re-run `auth import` daily.

### Getting your token by hand

1. Sign in to Planbook, open DevTools **Network** tab, filter `api.planbook.com`.
2. Reload, click the `getClasses2` request.
3. Right-click > **Copy** > **Copy as cURL**.
4. Run `planbook auth token` and paste.

## Caveats

- No published API exists yet; endpoints may change. See [docs/API-NOTES.md](docs/API-NOTES.md).
- `app.planbook.com` is behind AWS WAF; `api.planbook.com` is not.
- Requests are serialized. No parallelism.
- Planbook's terms (2020-07-01) have no anti-automation clause but reserve rate limits and discretionary termination.

There's evidence of a sanctioned API-key mechanism. If you depend on this tool, ask support@planbook.com.

## Licence

MIT.

## Releasing (maintainer)

Release-please gathers `main` merges into a version-bump PR. Merge it to tag and
publish to PyPI.

`feat:` bumps minor, `fix:` bumps patch. Squash-merge PRs with a conventional title.

The release PR is opened by the Actions bot. GitHub doesn't run CI on bot-opened
PRs, so close and reopen it once (`gh pr close N && gh pr reopen N`). To skip this
permanently, give release-please a fine-grained PAT.

First publish: create `planbook-cli` on PyPI, add a trusted publisher (workflow
`publish.yml`, environment `pypi`), add a GitHub environment named `pypi`.
