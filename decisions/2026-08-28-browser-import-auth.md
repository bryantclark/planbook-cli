---
name: browser-import-auth
date: 2026-08-28
description: Default auth reads the token from the user's browser rather than driving one
tags: [auth]
---

# Import from browser as default auth

`auth import` reads the JWT from the user's existing browser session. Google
rejects OAuth inside automation-controlled browsers ("this browser or app may
not be secure"), and this sidesteps that by not being one. The user signs in
normally; the CLI reads the cookie store afterward.
