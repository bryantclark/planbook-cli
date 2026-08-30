# Remaining work

Working list. Delete this file before the final push.

## BLOCKED - needs one action from Bryant
`planbook auth import` times out on an unanswered macOS Keychain prompt, so I
cannot get a token. Run it in your own terminal and click **Always Allow**:

    planbook auth import && planbook auth status

Until then everything needing a live call is stalled. Offline work continues.

## 1. Loop review
- [x] Full pass 1 (Claude) - fixed: updatedFields data loss, events delete
      --dry-run deleting, cross-year date comparison, raw --json ignored,
      bulk dry-run/validation gaps, self-asserting test
- [x] Full pass 2 (codex/gpt-5.6) - fixed: customStart/startTime carry-over
      blanking times, unitId/lessonLock/extraLesson reset on every edit,
      missing events create --force, todo rollback, OSError exit code
- [ ] Full pass 3 - must come back CLEAN for the loop to converge
- [ ] Comment-cleanup agent (loop mode requires one per full pass)

## 2. Codex test
- [x] integrations/codex-AGENTS.md written and installed to ~/.codex/AGENTS.md
- [x] codex CLI present (0.145.0) and authed
- [ ] Fresh low-context codex agent builds a week of plans, no CLI hint
- [ ] Fix what its process notes expose

## 3. Live verification (BLOCKED on token)
- [x] Offline dry-run sweep: all 11 pass
- [x] Exit codes verified: 64 usage / 77 no-auth / 0 ok
- [ ] Every one of the 49 commands exercised against the account
- [ ] Remove scratch data afterwards

## 4. Gates - all green as of 96b6e97
- [x] pytest 75 passed
- [x] mypy strict clean
- [x] ruff check + format clean
- [ ] CI green on GitHub (re-check after final push)

## 5. Docs truth pass
- [x] AGENTS.md GET/JSON correction, read-before-write cost, command table
- [x] README endpoint count destaled
- [ ] Final pass: every subcommand --help vs AGENTS.md and SKILL.md, one by one

## 6. Stretch - only with a captured request
- [ ] filterNotes / bumpLesson / extendLesson: each wants an unnamed int param
- [ ] Attendance write path: none exists under /services/planbook/attendance/*

## 7. Finish
- [ ] Delete TODO.md, final push, report
