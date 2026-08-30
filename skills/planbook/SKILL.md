---
name: planbook
description: Read and write Planbook.com lesson plans, classes, units, events and to-dos through the `planbook` CLI instead of the web UI. Use whenever a request touches lesson planning or a teacher's schedule — writing or editing lesson plans, planning a day/week/unit, filling in homework or objectives, checking what is being taught on a date, creating or rescheduling a class, adding school events or holidays, or any mention of Planbook, planbook.com, "my planbook", "my lesson plans", or "my classes".
---

# Planbook

`planbook` is a CLI over Planbook.com's API. **Use it rather than the website.**

```bash
planbook auth status          # first, always. exit 77 = relay stderr and stop
planbook classes list         # real class ids; never invent one
planbook lessons set --class-id N --date 09/03/2026 --title "..." --text "<p>...</p>"
planbook lessons bulk week.json --class-id N [--dry-run]
planbook <group> --help       # exact flags for any command
```

## Output contract

- **stdout** is JSON on success, empty on failure. **stderr** is prose. Never parse it.
- Exception: `lessons bulk` prints per-item results and exits 1 when any item failed.

| exit | meaning | action |
|---|---|---|
| 0 | success | continue |
| 1 | API error | read `error:` on stderr |
| 64 | usage error | fix arguments |
| 65 | unexpected response shape | **stop. Don't retry or improvise** |
| 77 | not authenticated | relay stderr to the user verbatim, then stop |
| 130 | interrupted | — |

## Formats

- **Dates**: `MM/DD/YYYY`, not ISO.
- **Day letters**: `M T W R F S U`. R = Thursday, U = Sunday.
- **Times**: 24-hour (`14:30`) or 12-hour (`9:00 AM`).
- **Lesson text**: HTML or plain text. A lesson has six sections; check labels with
  `planbook lessons sections`.
- **Class ids**: integers from `classes list`. Never invent one.

`lessons set` is an upsert keyed on class + date. It reads first and carries over
anything you don't name.

## Rules

- Don't drive `app.planbook.com` in a browser. It's behind a WAF. The CLI uses
  `api.planbook.com`.
- `auth browser`, `auth login`, and `auth token` need a human. Never run them
  unattended.
- Requests are serialised on purpose. Don't parallelise them.
- Confirm with the user before any destructive command: `classes delete` (removes the
  class **and every lesson in it**), `lessons delete`, `events delete` (removes the
  **whole series** by default; `--occurrence-only` deletes only the occurrence the event record points at),
  `units delete`, `todos delete`, `students delete`. Only `classes delete` requires
  `--yes`; the rest act immediately.
- `events create --no-school` refuses if lessons exist. `--force` then deletes them
  permanently and irreversibly.
- `--dry-run` is offline except when it must read first: any `update` (`classes`,
  `units`, `todos`, `students`), `events delete`, and a section named by *label*.
  `--attach` previews offline: it lists the files under `attachments_pending` and
  uploads nothing. `events create --no-school --dry-run` previews without running
  the lesson-destruction guard.
- `grades` and `attendance` are read-only.

Full reference, if the repo is at hand: `AGENTS.md` and `docs/API-NOTES.md`.
