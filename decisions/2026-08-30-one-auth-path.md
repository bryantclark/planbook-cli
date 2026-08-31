---
name: one-auth-path
date: 2026-08-30
description: Token import is the only sign-in, with paste as the manual fallback
tags: [auth]
---

# One auth path

The CLI signs in one way: `planbook auth import` reads the bearer token from the
cookie store of a browser the teacher is already signed in to. `auth token`
accepts one pasted by hand when the cookie store can't be read.

## Why

- Every request the API accepts is authorised by that bearer token. Any other
  sign-in mechanism would end at the same token, with more moving parts and a
  wider credential surface for no gain.
- The accounts this was built for sign in through SSO. Only the identity
  provider's own browser flow can complete that, so the CLI stays out of it and
  reads the result.
- One path is one thing to document, one thing to test, and one thing to
  replace.

## Consequence

`LoginFailed` comes only from the cookie reader. The CLI has no credential
prompt, and holds nothing but the token.

Replacing both remaining paths with a real OAuth client is tracked in
[docs/PRODUCTION-READINESS.md](../docs/PRODUCTION-READINESS.md).
