---
name: bearer-over-cookie
date: 2026-08-28
description: Send the JWT as Authorization Bearer rather than as a cookie
tags: [api, auth]
---

# Bearer header over cookie

`Authorization: Bearer <jwt>` authenticates with no cookies at all — verified
working. This avoids managing cookie jars and sidesteps the `SESSION` decoy
(which the server issues to unauthenticated callers). The JWT is the
`U|<view-id>|.accesstoken` cookie value extracted from the browser.
