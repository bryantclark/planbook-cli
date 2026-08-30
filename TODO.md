# Remaining work

Delete before the final push.

## Loop review
- [x] Pass 1 (Claude), Pass 2 (codex), Pass 3, Pass 4 - each found real defects, all fixed
- [ ] Pass 5 - running (correctness + comment cleanup). Loop converges when a pass is clean.

Defects found and fixed across the passes:
- token identity: two issuer claim-shapes, only one parsed -> every id null
- full-replace data loss carried over for lessons, todos, classes, units, students
- lessons --start-time/--end-time silently ignored by server -> removed
- notes / standards-report unreachable -> marked blocked, not offered
- events delete --dry-run performed the delete; classes update --dry-run ignored
- create_class reported ok when nothing was created -> raises
- raw -F collapsed repeated keys; raw --get/--json now mutually exclusive
- --attach uploaded before validating all refs; dry-run omitted attachments
- dates now validated locally (parse_date) instead of reaching a Java NPE
- EOFError from an unattended prompt now exits 64
- every create returns the new id for chaining

## Live verification (needs a fresh token - BLOCKED)
Token expired mid-session (auth-server tokens last 1h). Re-auth:
    planbook auth import && planbook auth status
Then confirm live (unit tests pass against mocks, but these field names are
inferred from the write side and want one live check):
- [ ] units update carry-over: unitDesc / unitStart / unitEnd / unitSection*Text
      really are the GET-side names
- [ ] students update carry-over: phoneNumber / parentEmailAddress / birthDate
      really are the getStudentsServlet names
- [ ] every create returns a correct id against the real add endpoints

## Blocked - needs a captured browser request
filterNotes, bumpLesson, extendLesson, getStandardsReport each want an integer
the server will not name. Attendance and grades have no write endpoint.

## Gates - green as of the last commit
- [x] pytest 86, mypy strict, ruff check + format
- [x] CI now runs all four gates on 3.10 and 3.13
- [ ] CI green after the final push

## Codex agent test (needs token)
- [x] codex-AGENTS.md installed and current
- [ ] Fresh low-context codex agent builds a week of plans, no CLI hint

## Finish
- [ ] Delete TODO.md, final push, report
