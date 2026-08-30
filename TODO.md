# Blocked on one action from you

The build is complete and the review loop has converged (nine correctness
passes, three comment passes, all green). Two things remain, and both need you:

## 1. Re-authenticate, then I can run the live verification
Auth-server tokens last one hour, so the session expired mid-build. Run:

    planbook auth import && planbook auth status

Then the last checks can run against the account:
- confirm the inferred GET-side field names for `units update`
  (unitDesc / unitStart / unitEnd / unitSection*Text) and `students update`
  (phoneNumber / parentEmailAddress / birthDate) - the carry-over logic is
  tested against mocks; only a live read confirms the real key spellings
- exercise all ~50 commands once against the account and remove scratch data

## 2. The Codex agent test needs Codex credits
The codex workspace ran out of credits during review pass 9. The skill and
`~/.codex/AGENTS.md` are installed and current, so once credits are refilled a
fresh low-context Codex agent can build a week of plans with no CLI hint.

## Still genuinely unreachable (need a captured browser request)
filterNotes, bumpLesson, extendLesson, getStandardsReport each demand an
integer the server refuses to name. Attendance and grades have no write path.

Delete this file once the live checks are done.
