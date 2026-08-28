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

Three ways in, in order of convenience.

**Browser sign-in - works with any account, including Google SSO:**

```bash
pip install 'planbook-cli[browser]'
planbook auth browser
```

This opens **your default browser** on Planbook's sign-in page - Brave, Chrome, Edge, Arc, Vivaldi, whichever handles `https://` on your machine. Firefox and Safari are not Chromium-based and cannot be driven; if one of those is your default, the CLI says so and falls back to Chrome. `--channel` overrides. You sign in however
you normally do; the CLI polls until a session actually works, then closes the
window. Your password is never typed into this tool and never passes through it.

The browser profile persists at `~/.config/planbook/browser-profile` (mode 0700),
and it holds your identity provider's session too. So **later runs refresh
silently and headlessly** - `planbook auth browser` only opens a window when the
stored sign-in has genuinely expired. `--interactive` forces a window anyway.

Sign-in happens on `auth.planbook.com`, never `app.planbook.com`: the app host is
behind an AWS WAF that challenges automated browsers, while the auth host is not
protected and is where the login form and SSO buttons live.

This is not the `gh auth login` pattern of bouncing through your default browser to
a localhost callback - that requires being a registered OAuth client of the service,
and Planbook offers no such thing. A controlled browser window is the closest
equivalent that can still capture the session automatically.

**Username and password**, for accounts that use Planbook's own login:

```bash
planbook auth login
```

**Paste a cookie**, if you would rather not install Playwright:

```bash
planbook auth cookie
```

It prompts with the input hidden. Pass it as an argument only in a script you
trust: the cookie is a bearer credential for the whole account, and an argument is
visible in shell history and in `ps`.

Find the value in DevTools: **Application -> Cookies -> `https://api.planbook.com` ->
`SESSION`**. It is HttpOnly, so it will not show up in `document.cookie`.

The session is stored at `~/.config/planbook/session.json`, mode 0600.
`PLANBOOK_SESSION` in the environment overrides it, which is the convenient way to
run in CI or a container.

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
