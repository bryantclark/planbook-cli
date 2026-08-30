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

- The password path was untested and unusable: the accounts in question sign in
  with SSO, so the form login could never work for them. Shipping a command that
  asks for a Planbook password and cannot use it is the worst credential
  surface in the tool.
- The browser path drove an automated browser, which identity providers refuse
  and which reads as impersonation. It needed an optional Playwright dependency
  to do it.
- Neither is what an official integration would use. Both were paths to the same
  bearer token `auth import` already gets without automating anything.

## Consequence

The `browser` optional dependency group is gone. `LoginFailed` now only comes
from the cookie reader. Sign-in is: sign in to Planbook in your browser, then
`planbook auth import`.

Replacing both remaining paths with a real OAuth client is tracked in
[docs/PRODUCTION-READINESS.md](../docs/PRODUCTION-READINESS.md).
