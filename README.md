# planbook-cli

An unofficial command-line interface for [Planbook.com](https://planbook.com), built
so that agents (and people) can read and write lesson plans without clicking through
the web UI.

Planbook publishes no API and no CLI. This tool talks to the private JSON API that
the Planbook web app itself uses, mapped by observing traffic from a signed-in
session. See [docs/API-NOTES.md](docs/API-NOTES.md) for exactly how, and
[AGENTS.md](AGENTS.md) for the agent-facing command reference.

## Status

Honest scope: this is not "all of Planbook". Four endpoints are fully mapped
(classes, class creation, lesson upsert, special days), three are partially mapped,
and about ten more have been observed but not wrapped in commands. Run
`planbook endpoints` for the current list.

Anything unmapped is still reachable through `planbook raw`, which POSTs to any path.

## Install

```bash
uv pip install -e .
```

## Quickstart

```bash
planbook auth login                 # prompts for email + password
planbook classes list
planbook lessons set --class-id 12345678 --date 09/03/2026 \
  --title "Photosynthesis" --text "<p>Chloroplasts and light reactions.</p>"
```

Every command prints JSON to stdout, so output pipes straight into `jq` or an agent.

## Authentication

`planbook auth login` performs the same form login as the website and stores the
resulting `SESSION` cookie in `~/.config/planbook/session.json`, mode 0600.

If your account signs in with Google, Microsoft, Clever, ClassLink, or Apple, the
form login cannot drive that. Sign in through a browser, copy the `SESSION` cookie,
and store it directly:

```bash
planbook auth cookie <SESSION-value>
```

`PLANBOOK_SESSION` in the environment overrides the stored file, which is the
convenient way to run in CI or a container.

## Caveats worth reading once

- **The API is undocumented and can change without notice.** When a response stops
  looking the way this tool expects, it raises a schema error and stops rather than
  guessing. That is deliberate: silently-wrong lesson plans are worse than a crash.
- **`app.planbook.com` is behind an AWS WAF; `api.planbook.com` is not.** This tool
  only ever talks to the API host. It does not attempt to defeat bot detection, and
  it identifies itself honestly in its User-Agent.
- **Requests are serialized on purpose.** No parallelism, no retry storms. This is
  somebody's real planbook.
- Planbook's terms (last updated 2020-07-01) contain no anti-automation or
  reverse-engineering clause, but they do reserve rate limits and allow account
  termination at their discretion. Use your own account. See the ToS section of
  docs/API-NOTES.md.

There is evidence of a sanctioned API-key mechanism (`/services/api/*` returns
"Invalid API Key. Please contact planbook.com administrator."). If you depend on this
tool, ask support@planbook.com about it before you build anything load-bearing.

## Licence

MIT.
