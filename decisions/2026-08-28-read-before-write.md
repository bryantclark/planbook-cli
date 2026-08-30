---
name: read-before-write
date: 2026-08-28
description: Every write reads the existing record first and carries over unmentioned fields
tags: [api, correctness]
---

# Read before every write

The server does full-record replace on `/updateLesson`, `/updateToDo`, and
`/updateClass/v10`. A payload built from defaults silently erases anything it
didn't restate. The CLI reads first and merges so callers don't have to pass
every field. This costs one extra request per write.
