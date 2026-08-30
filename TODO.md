# Remaining work

Working list. Delete this file before the final push.

## 1. Loop review to convergence
- [ ] Second full K3 pass (the loop only converges on a *clean* full pass)
- [ ] Comment-cleanup agent in parallel (required by loop mode)
- [ ] Fix everything it finds; re-run gates
- [ ] Repeat until a full pass is clean (max 5 passes, then hand back)

## 2. Codex discoverability + test
- [x] `integrations/codex-AGENTS.md` written
- [x] Installed into `~/.codex/AGENTS.md`
- [ ] Verify Codex actually reads it (check `codex` CLI is authed)
- [ ] Fresh low-context Codex agent builds a week of plans, no CLI hint
- [ ] Collect its process notes; fix what they expose

## 3. Verification sweep
- [ ] Every command exercised live against the account (not just --help)
- [ ] `--dry-run` verified on every command that advertises it
- [ ] Exit codes verified against the AGENTS.md table
- [ ] Token never in argv/logs; re-check after all edits
- [ ] Remove scratch data from the account

## 4. Quality gates (must all pass at the end)
- [ ] `pytest -q`
- [ ] `mypy` (strict)
- [ ] `ruff check src tests`
- [ ] `ruff format --check src tests`
- [ ] CI green on GitHub

## 5. Docs truth pass
- [ ] AGENTS.md matches actual `--help` output, command by command
- [ ] SKILL.md matches
- [ ] README install/auth instructions still correct
- [ ] docs/API-NOTES.md conventions all still true
- [ ] endpoints registry counts match reality

## 6. Stretch (only if a capture becomes possible)
- [ ] `filterNotes` - unnamed Long param
- [ ] `bumpLesson` / `extendLesson` - unnamed Integer param
- [ ] Attendance write path (none found under /attendance/*)

## 7. Finish
- [ ] Delete TODO.md
- [ ] Final push, report
