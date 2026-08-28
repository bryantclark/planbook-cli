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

**Import from your browser.** The recommended path.

```bash
planbook auth import
```

Sign in to Planbook in your normal browser - normal window, normal Google
session - then run that. It reads the one cookie it needs out of your browser's
cookie store, verifies it, and stores it.

Nothing is automated and no browser is driven, which is the point: Google
rejects OAuth inside automation-controlled browsers ("this browser or app may
not be secure"), and this sidesteps that entirely by not being one.

macOS gates the cookie store behind the Keychain, so the first run raises a
prompt. That prompt is the consent boundary and it is meant to be there; choose
**Always Allow** to make later runs silent.

**Paste a token**, if you would rather not grant Keychain access:

```bash
planbook auth token
```

It accepts the bare JWT, a whole `Cookie:` header, or an entire "Copy as cURL"
paste, and verifies before storing. See "Getting your token by hand" below.

**Username and password**, for accounts using Planbook's own login rather than SSO:

```bash
planbook auth login
```

**Browser sign-in** (`planbook auth browser`) drives its own browser window. It is
kept for completeness but is not recommended: Google and other identity providers
refuse to sign in inside an automated browser.

The token is stored at `~/.config/planbook/token.json`, mode 0600.
`PLANBOOK_TOKEN` in the environment overrides it, which is how to run in CI.

**Tokens last about 22 hours.** There is no refresh endpoint, so re-running
`planbook auth import` is the daily ritual - one command, no copying.

## Getting your token by hand

Sign in to Planbook in your normal browser, then:

Sign in to Planbook in your normal browser, then open DevTools:

1. **Network** tab, type `api.planbook.com` in the filter box
2. reload the page, click the **`getClasses2`** request
3. right-click it -> **Copy** -> **Copy as cURL**
4. run `planbook auth token` and paste the whole thing

**The credential is the cookie named `U|<view-id>|.accesstoken`, not `SESSION`.**
`api.planbook.com` issues a `SESSION` to unauthenticated callers too, so DevTools
shows a convincing decoy beside the real thing. Copy-as-cURL avoids the whole
problem: a request that actually succeeded cannot be carrying the wrong credential.

Both cookies are HttpOnly, so neither appears in `document.cookie`.

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
