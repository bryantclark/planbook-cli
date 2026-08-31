---
name: one-mutation-seam
date: 2026-08-30
description: All writes run through mutations.py, which owns dry-run previews, ordering and postcondition checks
tags: [api, correctness, safety]
---

# One mutation seam

Every resource module used to reimplement the same five steps in its own order:
read the current record, build a complete payload, preview it for `--dry-run`,
send it, decide whether it took. The ordering *is* the safety property — the
server replaces whole records and answers HTTP 200 whether or not it stored
anything — so five copies meant five chances to get it wrong, and a `--dry-run`
that had already drifted into performing the delete it was meant to preview.

A write is now a `Mutation`, and `mutations.py` owns what happens to it:

- `preview()` renders the exact requests, so a dry run and the real run cannot
  disagree about what would be sent.
- `commit()` sends them in order and then re-reads the record. A create or an
  update must be found; a delete must be gone. Otherwise it raises
  `PostconditionFailed`.
- `require_intent()` applies one destructive-action policy: `--yes` is required
  when a delete destroys records the caller did not name, and the `cascade`
  count is reported by `--dry-run` either way.
- `resolve_created()` recovers the id of a created record by diffing the list
  and narrowing by the fields just written, so a create returns a real `id`
  instead of `null` with instructions to go and look.

The cost is one extra read per write. That is the right trade for somebody's
real planbook, and it is documented in AGENTS.md so a bulk run can budget it.
