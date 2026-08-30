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

Full reference: `AGENTS.md` and `docs/API-NOTES.md`.
