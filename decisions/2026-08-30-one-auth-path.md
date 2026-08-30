---
name: one-auth-path
date: 2026-08-30
description: Password login and the automated browser are removed; import is the only sign-in
tags: [auth]
---

# One auth path

`auth login` (Spring form login with a password) and `auth browser` (Playwright
driving a headed browser) are removed. `auth import` stays, with `auth token` as
the manual fallback.

## Why

- The password path was untested and unusable: the accounts in question use SSO,
  so the form login never worked. A command that asks for a password it can't
  use is the worst credential surface in the tool.
- The browser path drove an automated browser. Identity providers refuse these,
  and it reads as impersonation. It pulled in an optional Playwright dependency.
- Neither is what an official integration would use. Both reached the same bearer
  token `auth import` already gets without automating anything.

## Consequence

The `browser` optional dependency group is gone. `LoginFailed` now only comes
from the cookie reader. Sign-in is: sign in to Planbook in your browser, then
`planbook auth import`.

Replacing both remaining paths with a real OAuth client is tracked in
[docs/PRODUCTION-READINESS.md](../docs/PRODUCTION-READINESS.md).
