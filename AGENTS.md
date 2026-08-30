# planbook-cli for agents

Installed as a skill (`skills/planbook/SKILL.md`), an agent should find this tool
without being told it exists. This file is the full contract behind that skill.

This file is the contract. If you are an agent driving this CLI, everything you need
is here; you should not need to read the source.

## Output contract

- **stdout is JSON on success, empty on failure.** On success stdout carries JSON and nothing else. On failure it is empty and the diagnosis goes to stderr, so branch on the exit code first, then parse stdout.
- **stderr is prose.** Diagnostics, request logs under `-v`. Never parse it.
- **Exit codes carry meaning:**

  | code | meaning | what to do |
  |---|---|---|
  | 0 | success | continue |
  | 1 | API reported an error | read `error:` on stderr; usually a bad field value |
  | 64 | usage error | you called it wrong; fix the arguments |
  | 65 | unexpected response shape | the API changed. **Stop.** Do not retry, do not guess |
  | 77 | not authenticated | token missing or expired; **relay the stderr message to the user verbatim** - it names the URL and the command |
  | 130 | interrupted | - |

Exit 65 means the server returned something this tool does not recognise. Retrying
will not help and improvising a workaround risks writing wrong data into a real
planbook. Surface it to a human.

## Formats

- **Dates are always `MM/DD/YYYY`.** Not ISO. `09/03/2026`.
- **Day specs are letters**: `M T W R F S U`. **R is Thursday, U is Sunday.**
  So a normal weekday class is `MTWRF`.
- **Times are 12-hour on the wire** ("9:00 AM"). The CLI accepts 24-hour too
  (`14:30`) and converts. Passing 24-hour straight to `raw` is silently stored as
  empty, losing the time.
- **Lesson text accepts HTML.** `<p>...</p>` renders as you would expect. Plain text
  works too.
- Class ids are integers, returned as `id` by `classes list`.

## Commands

Run `planbook <group> --help` for exact flags. Groups:

| group | what it does |
|---|---|
| `auth` | `status`, `import`, `token`, `browser`, `login`, `logout` |
| `classes` | `list`, `get`, `create`, `update`, `delete` |
| `lessons` | `set`, `bulk`, `get`, `delete`, `week`, `sections` |
| `units` | `list`, `create`, `update`, `delete` |
| `events` | `list`, `create`, `delete` |
| `todos` | `list`, `create`, `update`, `delete` |
| reads | `assignments`, `assessments`, `schools`, `templates`, `standards`, `comments`, `attachments`, `settings`, `schedule special-days` (each takes a subcommand only where shown) |
| `students` | `list`, `create`, `update`, `delete` |
| `attendance` | read attendance for a class on a date (read-only) |
| `grades` | grade periods and scored assignments |
| `templates` | lesson templates |
| `raw` | POST to any endpoint; `--get` for GET-only paths, `--json` for JSON bodies |
| `endpoints` | what is mapped and what is not |

### Authentication


```bash
planbook auth status          # verify the token works; cheap, safe to call first
planbook auth import          # read the token from the user's browser
planbook auth browser         # discouraged; opens its own browser window
planbook auth login           # prompts for a password on a TTY - NOT for agents
planbook auth token           # stores a pasted token - NOT for agents
planbook auth logout
```

`auth status` and `auth logout` are always safe unattended. So is `auth import`,
though it may raise a macOS Keychain prompt the user has to approve.

**Tokens last about 22 hours (1 hour for auth-server tokens).** On exit 77, the stderr message already contains
the full remedy - a sign-in URL and the exact command. Show it to the user rather
than paraphrasing, then run `planbook auth import` once they say they have signed
in. Do not try to sign in yourself.

`auth import` is safe to try once on exit 77: it reads the token from a browser the
user is already signed in to. It may raise a macOS Keychain prompt the user has to
approve, and it fails cleanly if no browser holds a usable token.

`auth browser`, `auth login` and `auth token` all need a human - `browser` opens a
window and waits, the other two prompt on a TTY. Never run them unattended. There is
no silent refresh: the token is minted on a WAF-protected host that only a headed
browser reaches.

### Reading

```bash
planbook classes list                     # classes + weekly schedule, readable keys
planbook classes list --raw               # unmapped wire format
planbook schedule special-days              # teacher and year id default from the token
planbook settings
planbook standards
planbook lessons week --monday 08/31/2026 [--weeks 3]
planbook endpoints                        # what is mapped and what is not
```

`classes list` gives you `id`, `name`, `start_date`, `end_date`, `year_id`,
`teacher_id`, and a `schedule` object with per-day `teaches`/`start`/`end`. Get the
class id from here before writing anything.

`lessons week` is **mapped**: it returns a list of days, each `{date, day_of_week,
lessons: [...]}`, where every lesson carries `class_id`, `class_name`, `lesson_id`,
`title`, `start`, `end`, `text`, `homework`, `notes`, `standards`, `assignments`
and `attachments`. It is the natural answer to "what am I teaching this week".
`--all` also includes class slots on a day that have no saved lesson; `--weeks N`
extends the range; `--raw` returns the undecoded body, which is the only form that
also carries calendar events.

### Writing

```bash
planbook lessons set --class-id 12345678 --date 09/03/2026 \
  --title "Photosynthesis" \
  --text "<p>Chloroplasts and the light reactions.</p>" \
  [--homework "Read ch. 4"] [--notes "Lab groups of 3"] [--dry-run]
```

A lesson has **six** text sections, not three. Sections 1-3 are Lesson, Homework
and Notes; 4-6 are named by the account's lesson layout and are "Not Used" until
configured. Run `planbook lessons sections` to see the labels, then write any of
them by number or label:

```bash
planbook lessons sections
planbook lessons set --class-id N --date D --section "Objectives=<p>...</p>" --section "4=..."
```

Attach standards, assignments and files to a lesson:

```bash
planbook standards --search "3.NBT"          # find the db_id
planbook lessons set --class-id N --date D \
  --standard 118071 --standard 118072 \
  --assignment 3865664 \
  --attach ./worksheet.pdf --attach existing-resource.pdf
```

Each of those **replaces** what was attached, so pass the full set you want. Standards
use the numeric `db_id`, not the human id. An assignment belongs to one class.
`--attach` uploads a local path or links an existing resource by name.

A lesson always shows its class period's times. `/updateLesson` accepts
`customStart` and `customEnd` and then ignores them, so there is no per-lesson
time override to set. Change the class schedule instead. Events do store times.

Class schedule times:

```bash
planbook classes create --name "Biology 1" --start 08/31/2026 --end 06/06/2027 \
  --days MWF --time "M=8:00-8:45" --time "W=13:00-13:50" --time "F=9:15-10:05"

# or one window for every teaching day
planbook classes create ... --days MTWRF --time 9:00-9:50
```

**`lessons set` is an upsert keyed on class + date**, and a true partial update:
it reads the lesson first and carries over anything you do not name. That read is
not optional - the server writes empty any text field it receives empty, so a
standards-only write would otherwise blank the lesson. It costs one extra request
per write, so a bulk file makes roughly two requests per lesson (more on a new
date that also attaches standards or files). Writing the same date twice
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
  handle this; `raw` does not. Sending `true`/`false` to the class endpoints is
  accepted and silently produces a class that teaches on no days.
- **`verifyShift=true` means "check, do not commit."** Events and classes accept it,
  answer exactly like success, and write nothing. Commit with `false`.
- **`scheduleChange=true` is required** when updating a class, or the rename lands
  and the new schedule is discarded.
- **`teachDay1` is Sunday**, not Monday, in the class schedule JSON.
- **`subjectId` means class id** on the unit endpoints, and nowhere else.
- **Integer fields must be `0` when absent, never `""`.** An empty string triggers a
  server-side Java `NullPointerException` returned as a 200. Again, `raw` does not
  handle this for you.
- **Most calls are form-encoded POST**, but not all: a few `/services/planbook/**`
  endpoints are GET-only and answer a POST with `405`, and a couple want a JSON
  body. `raw --get` and `raw --json` cover both. A 405 in an error message means
  "use `--get`".
- **Failure arrives as HTTP 200** with `{"error":"true","msg":"..."}`. This tool
  detects that and exits non-zero, so you can trust the exit code.

## Before you write

1. `planbook auth status` - confirm the session (exit 77 means stop).
2. `planbook classes list` - get the real `id`; never guess one.
3. `--dry-run` first on anything generated, to see the exact payload.
4. Then write.

## Destructive commands

These delete data with no undo. Confirm with the user before running them.

- `classes delete --class-id N --yes` - removes the class **and every lesson in it**. The
  `--yes` flag is required.
- `lessons delete --class-id N --date D` - clears one lesson.
- `events delete --event-id N` - removes the **whole repeating series** by default; pass
  `--occurrence-only` for just that date.
- `units delete --unit-id N --class-id N` - removes one unit.
- `todos delete --todo-id N` - removes one to-do.
- `students delete --student-id N` - removes one student immediately; no `--yes`,
  no `--dry-run`.

## Things this tool will not do

- `grades` and `attendance` are **read-only**; there is no write endpoint for either.
- Seating charts, lesson banks, messages and reporting are not mapped;
  `planbook endpoints` shows what `raw` might reach.
- Notes are unreachable: `filterNotes` wants an integer the server will not name,
  so it is not offered as a command (see `planbook endpoints`). `templates` works
  and needs no arguments.
- Sign you in. Every auth path needs a human.
