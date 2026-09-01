---
name: planbook
description: Read and write Planbook.com lesson plans, classes, units, events and to-dos through the `planbook` CLI instead of the web UI. Use whenever a request touches lesson planning or a teacher's schedule — writing or editing lesson plans, planning a day/week/unit, filling in homework or objectives, checking what is being taught on a date, creating or rescheduling a class, adding school events or holidays, or any mention of Planbook, planbook.com, "my planbook", "my lesson plans", or "my classes".
---

# Planbook

`planbook` is a CLI over Planbook.com's API. **Use it rather than the website.**

```bash
planbook check                # first, always. session + hours left + class ids
planbook schema               # every command and flag as JSON; read this, not --help
planbook lessons set --class-id N --date 09/03/2026 --title "..." --text -
planbook lessons bulk week.json --class-id N [--dry-run] [--journal r.jsonl --resume]
```

- Run with `--error-json` so failures arrive as `{"error": {"kind", "code",
  "retryable", "remedy"}}` instead of prose. Exit 77 means a human must sign in:
  relay stderr verbatim and stop.
- `-` on a text flag reads that value from stdin. Use it for HTML.
- Every list answers to `id`. Every `create` returns `id`, never `null`.
- `--dry-run` prints the exact requests. Deletes that destroy records you did
  not name also need `--yes`; the preview reports the `cascade` count. So does
  every `raw` request but `--get`: nothing can tell what an unmapped POST does.

Full reference: `AGENTS.md` and `API-NOTES.md` beside this file, if they were
installed with it; otherwise github.com/bryantclark/planbook-cli.
