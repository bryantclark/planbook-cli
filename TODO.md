# Remaining work

Working list. Delete this file before the final push.

## 1. Loop review
- [x] Pass 1 (Claude) - updatedFields data loss, events delete --dry-run
      deleting, cross-year date compare, raw --json ignored, bulk gaps
- [x] Pass 2 (codex) - customStart/startTime carry-over, unitId/lessonLock
      reset, missing events create --force, todo rollback, OSError exit code
- [ ] Pass 3 - running; must come back clean for the loop to converge
- [ ] Comment-cleanup agent - running

## 2. Live verification - DONE
- [x] All 20 command groups exercised against the account
- [x] Full CRUD: classes, lessons, todos, units, events, students, attachments
- [x] Read-modify-write verified live on lessons and classes
- [x] Scratch data removed (one attachment remains; no delete endpoint exists)

Found and fixed in the sweep:
- token identity claims: two issuer shapes, only one parsed -> every id null
- teacher/year id now fall back to a live lookup
- lessons --start-time/--end-time silently ignored by the server -> removed
- notes and standards-report can never succeed -> marked blocked, not offered
- ids were half positional, half flags -> all named now

## 3. Gates
- [x] pytest 75, mypy strict, ruff check + format
- [ ] Re-run after the comment pass
- [ ] CI green on GitHub after the final push

## 4. Docs
- [x] AGENTS.md, SKILL.md, API-NOTES corrected for all of the above
- [x] Every documented flag cross-checked against --help (0 mismatches)

## 5. Codex agent test
- [x] integrations/codex-AGENTS.md installed to ~/.codex/AGENTS.md
- [ ] Fresh low-context codex agent builds a week of plans, no CLI hint
- [ ] Fix what its process notes expose

## 6. Blocked - needs a captured browser request
filterNotes, bumpLesson, extendLesson, getStandardsReport each want an integer
the server refuses to name. Every plausible spelling tried. Attendance has no
write endpoint at all.

## 7. Finish
- [ ] Delete TODO.md, final push, report
