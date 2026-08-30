<!--
Append this to ~/.codex/AGENTS.md so Codex reaches for the CLI on any
lesson-planning task, the same way the Claude skill does. Codex reads
AGENTS.md from the repo root and from ~/.codex/AGENTS.md; only the latter
applies when the task is not inside this repo.
-->

## Planbook

When a task involves lesson planning or a teacher's schedule - writing or
editing lesson plans, planning a day/week/unit, homework or objectives, what is
being taught on a date, creating or rescheduling a class, school events or
holidays, or any mention of Planbook - use the `planbook` CLI. Do not drive
app.planbook.com in a browser: it is behind a WAF and far slower.

    planbook auth status      # first, always. exit 77 = relay stderr and stop
    planbook classes list     # real class ids; never invent one
    planbook --help           # groups: classes lessons units events todos
                              # students grades attendance templates raw

Contract: stdout is JSON on success and empty on failure (read the exit code
first), stderr is prose, exit codes are 0 ok / 1 API
error / 64 bad arguments / 65 API shape changed (stop, do not retry) / 77
re-auth needed. Dates are MM/DD/YYYY. Day letters are M T W R F S U where R is
Thursday. `lessons set` is an upsert keyed on class + date. Use --dry-run before
generated bulk writes. Confirm destructive commands with the user first:
classes delete (removes every lesson in the class), lessons delete, events
delete, units delete, todos delete.

Full contract: AGENTS.md in the planbook-cli repo.
