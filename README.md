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

**Paste a session cookie.** This is the supported path, and the one to use.

```bash
planbook auth cookie
```

It prompts with the input hidden, so the cookie stays out of your shell history
and out of `ps`. To find the value, see "Getting your session cookie" below.

The session is stored at `~/.config/planbook/session.json`, mode 0600.
`PLANBOOK_SESSION` in the environment overrides it, which is how to run in CI or a
container.

**Username and password**, for accounts using Planbook's own login rather than SSO:

```bash
planbook auth login
```

**Browser sign-in** (`planbook auth browser`, needs the `[browser]` extra) exists but
is not recommended. It has to launch its own browser window with its own profile,
because the credential is a cookie that can only be read from a browser this tool
controls - it cannot use your everyday window. That makes it clumsier than pasting.
It is kept for the day Planbook registers an OAuth client, which would replace it
with a proper redirect flow. See docs/API-NOTES.md.

## Getting your session cookie

Sign in to Planbook in your normal browser, then:

**Reliable method - Network tab.** Open DevTools, go to **Network**, reload the page,
and click any request to `api.planbook.com`. Under **Request Headers**, copy the
value after `Cookie: SESSION=`. This shows exactly what the API host receives, which
is what the CLI needs.

**Alternative - Application tab.** DevTools -> **Application** -> **Cookies** ->
`https://api.planbook.com` -> `SESSION`. If that origin is not listed, load your
planbook first so the app calls the API, then look again.

The cookie is HttpOnly, so it will not appear in `document.cookie`.

It expires eventually. When commands start exiting 77, repeat these steps.

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
