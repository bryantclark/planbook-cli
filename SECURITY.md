# Security

## Reporting a vulnerability in this tool

Email bryant@k3.is. Please do not open a public issue. Expect a reply within a
week.

## Reporting something about Planbook.com

This project is not affiliated with Planbook.com. Anything about their service
belongs to support@planbook.com, not here. Findings from building this tool
were reported to Planbook directly; this repository does not publish
exploitable detail about their platform.

## What this tool does with your credentials

- The credential is your own Planbook access token — a JWT the web app already
  holds. `auth import` reads it from your browser's cookie store; `auth token`
  takes one you paste. Nothing else is collected.
- It is stored at `~/.config/planbook/token.json`, file mode 0600, in a
  directory created 0700. `PLANBOOK_TOKEN` overrides the file for CI.
- It is sent to `api.planbook.com` over HTTPS as `Authorization: Bearer`, and
  nowhere else. There is no telemetry, no analytics, and no other network
  destination in this codebase.
- Passwords, when `auth login` is used, are read from the terminal. They are
  never written to disk, never placed in `argv`, and never logged.
- `--verbose` logs request URLs and field *names* to stderr. It does not log
  the token or field values.
- `auth logout` deletes the stored token.

Tokens expire on their own — about 22 hours, or 1 hour for auth-server tokens.
There is no refresh endpoint on the private API, so an expired token simply
stops working.

## What it does with student data

Lesson plans, rosters, grades, and attendance are read on demand and printed to
stdout. Nothing is cached, stored, or sent anywhere else. If you pipe that
output into another program — including an AI assistant — the data goes wherever
that program sends it. That is your decision to make, and in a school setting it
is likely governed by your district's agreements.

Use your own account only.

## Known limits

- The private API is undocumented and can change without notice; the tool fails
  loudly rather than guessing when a response changes shape.
- Writes replace whole records server-side. Every write reads first and carries
  existing fields over. `--dry-run` is available on writes.
- Creating a no-school event permanently deletes that date's lessons. This is
  Planbook's behaviour; the CLI warns before doing it.

See [docs/PRODUCTION-READINESS.md](docs/PRODUCTION-READINESS.md) for the auth
model this should be replaced with, and what it would take.
