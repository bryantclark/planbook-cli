---
name: fail-on-schema-drift
date: 2026-08-28
description: Raise SchemaDrift and stop rather than parsing unexpected responses optimistically
tags: [api, correctness]
---

# Fail on schema drift

When a response doesn't match the expected shape, the CLI raises `SchemaDrift`
(exit 65) and stops. Retrying or improvising risks writing wrong data into a
real planbook. A crash is recoverable; silently wrong lesson plans are not.
