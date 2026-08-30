---
name: serial-requests
date: 2026-08-28
description: All requests are sent one at a time with no retry loops
tags: [api, safety]
---

# Serial requests only

No parallelism, no retry storms. Planbook's terms reserve rate limits and allow
discretionary termination. This is somebody's real planbook — a request storm
that corrupts data or triggers a ban isn't worth the speed.
