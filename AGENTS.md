# planbook-cli for agents

This file is the contract. If you are an agent driving this CLI, everything you need
is here; you should not need to read the source.

## Output contract

- **stdout is always JSON.** Nothing else is ever written there. Parse it directly.
- **stderr is prose.** Diagnostics, request logs under `-v`. Never parse it.
- **Exit codes carry meaning:**

  | code | meaning | what to do |
  |---|---|---|
  | 0 | success | continue |
  | 1 | API reported an error | read `error:` on stderr; usually a bad field value |
  | 64 | usage error | you called it wrong; fix the arguments |
  | 65 | unexpected response shape | the API changed. **Stop.** Do not retry, do not guess |
  | 77 | not authenticated | session missing or expired; a human must re-auth |
  | 130 | interrupted | - |

Exit 65 means the server returned something this tool does not recognise. Retrying
will not help and improvising a workaround risks writing wrong data into a real
planbook. Surface it to a human.

## Formats

- **Dates are always `MM/DD/YYYY`.** Not ISO. `09/03/2026`.
- **Day specs are letters**: `M T W R F S U`. **R is Thursday, U is Sunday.**
  So a normal weekday class is `MTWRF`.
- **Lesson text accepts HTML.** `<p>...</p>` renders as you would expect. Plain text
  works too.
- Class ids are integers, returned as `id` by `classes list`.

## Commands

### Authentication

```bash
planbook auth status          # verify the session works; cheap, safe to call first
planbook auth browser         # opens a browser for a human - NOT for agents
planbook auth login           # prompts for a password on a TTY - NOT for agents
planbook auth cookie          # prompts for a cookie, hidden - NOT for agents
planbook auth logout
```

**Only `auth status` and `auth logout` are safe to run unattended.** The other three
all need a human: `browser` opens a window and waits, `login` and `cookie` prompt on
a TTY. If `auth status` exits 77, stop and ask a human to sign in - do not try to
authenticate yourself.

### Reading

```bash
planbook classes list                     # classes + weekly schedule, readable keys
planbook classes list --raw               # unmapped wire format
planbook schedule special-days --teacher-id N --year-id N
planbook settings
planbook standards
planbook lessons week --monday 08/31/2026 [--weeks 3]
planbook endpoints                        # what is mapped and what is not
```

`classes list` gives you `id`, `name`, `start_date`, `end_date`, `year_id`,
`teacher_id`, and a `schedule` object with per-day `teaches`/`start`/`end`. Get the
class id from here before writing anything.

`lessons week` is **partially mapped**: the call works but the response is passed
through unmodified because the `days` structure has not been decoded. Treat its
output as raw, and do not build logic on its internals.

### Writing

```bash
planbook lessons set --class-id 12345678 --date 09/03/2026 \
  --title "Photosynthesis" \
  --text "<p>Chloroplasts and the light reactions.</p>" \
  [--homework "Read ch. 4"] [--notes "Lab groups of 3"] [--dry-run]
```

**`lessons set` is an upsert keyed on class + date.** Writing the same date twice
edits the existing lesson in place; it does not create a duplicate. This makes it
safe to re-run, and it is the main reason to use this tool over Planbook's CSV
import, which is append-only.

Bulk writes:

```bash
planbook lessons bulk lessons.json [--class-id N] [--keep-going] [--dry-run]
```

where `lessons.json` is a list of objects using the same keys:

```json
[
  {"class_id": 12345678, "date": "09/07/2026", "title": "Week 2 Day 1",
   "text": "<p>Cell membranes.</p>"},
  {"date": "09/08/2026", "title": "Week 2 Day 2", "text": "<p>Osmosis.</p>"}
]
```

Items without `class_id` fall back to `--class-id`. Requests are sent serially, in
order. By default the run stops at the first failure; `--keep-going` records the
error and continues, and the command still exits non-zero if anything failed.

Creating a class:

```bash
planbook classes create --name "Biology 1" --start 08/31/2026 --end 06/06/2027 \
  --days MTWRF [--color '#7ED321'] [--description "..."]
```

### Unmapped endpoints

```bash
planbook raw /getAssignments
planbook raw /getAttachmentList -F teacherId=123 -F withAllFolders=true
```

`raw` POSTs form-encoded fields to any path and prints whatever comes back. Use it
for anything `planbook endpoints` lists as `observed`. Field conventions still apply
(see below).

## Field conventions that will bite you

These come from the server's own behaviour, not from style preference:

- **Booleans are the strings `Y` and `N`**, not `true`/`false`. The wrapped commands
  handle this; `raw` does not.
- **Integer fields must be `0` when absent, never `""`.** An empty string triggers a
  server-side Java `NullPointerException` returned as a 200. Again, `raw` does not
  handle this for you.
- **Every call is POST**, form-encoded. There are no GET endpoints and no JSON bodies.
- **Failure arrives as HTTP 200** with `{"error":"true","msg":"..."}`. This tool
  detects that and exits non-zero, so you can trust the exit code.

## Before you write

1. `planbook auth status` - confirm the session (exit 77 means stop).
2. `planbook classes list` - get the real `id`; never guess one.
3. `--dry-run` first on anything generated, to see the exact payload.
4. Then write.

## Things this tool will not do

- Delete a class or a lesson. Not mapped; do it in the web UI.
- Grades, attendance, students, seating charts, units, templates, lesson banks,
  messages, reporting. Observed or untouched. `raw` may reach some of them.
- Drive `app.planbook.com`. That host sits behind an AWS WAF and this tool does not
  go near it.
