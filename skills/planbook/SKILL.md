---
name: planbook
description: Read and write Planbook.com lesson plans, classes, units, events and to-dos through the `planbook` CLI instead of the web UI. Use whenever a request touches lesson planning or a teacher's schedule — writing or editing lesson plans, planning a day/week/unit, filling in homework or objectives, checking what is being taught on a date, creating or rescheduling a class, adding school events or holidays, or any mention of Planbook, planbook.com, "my planbook", "my lesson plans", or "my classes".
---

# Planbook

`planbook` is a CLI over Planbook.com's API. **Use it rather than the website.** Do
not try to drive `app.planbook.com` in a browser: it sits behind a WAF, it is far
slower, and everything you need is a command.

## First, always

```bash
planbook auth status
```

- **Exit 0** — you are signed in. The output names the account and hours of token left.
- **Exit 77** — not signed in. The stderr message contains the sign-in URL and the
  exact command. **Relay it to the user verbatim** and stop; you cannot sign in for
  them. Once they say they have signed in, run `planbook auth import`.

Then get the real class ids — never invent one:

```bash
planbook classes list
```

## The contract

- **stdout is always JSON.** Parse it. Nothing else is written there.
- **stderr is prose.** Never parse it.
- **Exit codes:** 0 ok · 1 API error · 64 bad arguments · 65 **API shape changed —
  stop, do not retry or improvise** · 77 re-auth needed.
- **Dates are `MM/DD/YYYY`**, never ISO.
- **Day letters are `M T W R F S U`** — R is Thursday, U is Sunday.
- **Times** accept `14:30` or `2:30 PM`; the CLI converts.
- Lesson and event text accept HTML (`<p>`, `<ul>`, `<strong>`).

## Writing lessons

`lessons set` is an **upsert keyed on class + date** — running it twice for the same
date edits in place, so it is safe to re-run.

```bash
planbook lessons set --class-id 12345678 --date 09/03/2026 \
  --title "Photosynthesis" \
  --text "<p><strong>Objective:</strong> explain how plants make food.</p>" \
  --homework "Read ch. 4" \
  --start-time 09:15 --end-time 10:05
```

A lesson has **six** sections, not three. Check what this account calls them:

```bash
planbook lessons sections
planbook lessons set --class-id N --date D --section "Objectives=<p>...</p>"
```

For a whole week, write a JSON file and send it in one go — it validates every item
before writing any, so a typo cannot half-apply a week:

```bash
planbook lessons bulk week.json --class-id 12345678
```

```json
[
  {"date": "09/07/2026", "title": "Place value", "text": "<p>...</p>",
   "homework": "Workbook p. 12", "start_time": "09:15", "end_time": "10:05"},
  {"date": "09/08/2026", "title": "Rounding", "text": "<p>...</p>"}
]
```

## Everything else

```bash
planbook classes  list|get|create|update|delete
planbook lessons  set|bulk|delete|week|sections
planbook units    list|create|update|delete
planbook events   list|create|delete
planbook todos    list|create|update|delete
planbook schedule special-days --teacher-id N --year-id N   # holidays
planbook endpoints                    # what is mapped; `raw` reaches the rest
planbook raw /anyEndpoint -F k=v      # escape hatch
```

Run `planbook <group> --help` for exact flags rather than guessing.

## Rules

- **Never invent a class id.** Read it from `classes list`.
- **`--dry-run` first** on anything generated in bulk. It needs no network for
  lessons, and prints the exact payload.
- **Destructive commands need confirming with the user first**: `classes delete`
  (removes every lesson in the class, and requires `--yes`), `lessons delete`,
  `events delete` (the whole repeating series unless `--occurrence-only`),
  `units delete`, `todos delete`.
- **On exit 65, stop.** The API changed shape; guessing corrupts real lesson plans.
- Requests are serialised on purpose. Do not parallelise them.

Full contract: `AGENTS.md` in the planbook-cli repo. Wire-format details and the
conventions that fail silently: `docs/API-NOTES.md`.
