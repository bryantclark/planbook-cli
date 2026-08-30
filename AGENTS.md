# Project agent instructions

Read these files before making project changes:

1. `STACK.md` for the stack, package manager, test runner, and common commands.
2. `CONTEXT.md` for domain vocabulary, core entities, and open questions.
3. `.ai/code-style.md` and `.ai/testing.md` when editing files matching their scope. `.ai/writing-style.md` applies to all prose you write, including chat replies.
4. `DECISIONS.md` for durable technical decisions that must not be contradicted silently.

## The planbook CLI

`planbook` is a CLI over Planbook.com's private API. Use it rather than the website.
Don't drive `app.planbook.com` in a browser — it's behind a WAF.

### First, always

```bash
planbook auth status
```

- **Exit 0** — signed in. Output names the account and hours of token left.
- **Exit 77** — not signed in. Stderr contains the sign-in URL and exact command.
  Relay it to the user verbatim and stop.

Then get real class ids:

```bash
planbook classes list
```

### Output contract

- **stdout** is JSON on success, empty on failure. Exception: `lessons bulk` prints per-item results and exits 1 when any item failed.
- **stderr** is prose diagnostics. Never parse it.
- **Exit codes:**

  | code | meaning | action |
  |---|---|---|
  | 0 | success | continue |
  | 1 | API error | read `error:` on stderr |
  | 64 | usage error | fix arguments |
  | 65 | unexpected response shape | **stop — do not retry or improvise** |
  | 77 | not authenticated | relay stderr to user verbatim |
  | 130 | interrupted | — |

### Formats

- **Dates:** `MM/DD/YYYY`. Not ISO.
- **Day letters:** `M T W R F S U`. R = Thursday, U = Sunday.
- **Times:** the CLI accepts 24-hour (`14:30`) or 12-hour (`9:00 AM`).
- **Lesson text:** HTML or plain text.
- **Class ids:** integers from `classes list`.

### Commands

Run `planbook <group> --help` for exact flags.

| group | subcommands |
|---|---|
| `auth` | `status`, `import`, `token`, `logout` |
| `classes` | `list`, `get`, `create`, `update`, `delete` |
| `lessons` | `set`, `bulk`, `get`, `delete`, `week`, `sections` |
| `units` | `list`, `create`, `update`, `delete` |
| `events` | `list`, `create`, `delete` |
| `todos` | `list`, `create`, `update`, `delete` |
| `students` | `list`, `create`, `update`, `delete` |
| `attendance` | read-only |
| `grades` | grade periods and scored assignments |
| `templates` | lesson templates |
| reads | `assignments`, `assessments`, `schools`, `standards`, `comments`, `settings`, `schedule special-days` |
| `attachments` | `list`, `upload`; link with `lessons set --attach` |
| `raw` | POST to any endpoint; `--get` for GET paths, `--json` for JSON bodies |
| `endpoints` | shows what is mapped |

Every `create` returns the new record's id, so you can chain without a second
lookup. Only `todo_id` is guaranteed. `class_id`, `unit_id`, `event_id` and
`student_id` are recovered by diffing the list around the write, so they come
back `null` if more than one record appeared — fall back to a `list`. `students
update` needs `--class-id` as well as `--student-id`.

`classes list` and `students list` normalise the id key to `id`. `units list`,
`todos list` and `events list` return undecoded wire records, keyed `unitId`,
`toDoId` and `eventId`.

### Authentication

`auth status` and `auth import` are safe unattended. `auth import` may raise a
macOS Keychain prompt. Without a TTY it never waits for you to sign in: it
succeeds if a browser or the stored session holds a usable token, and exits 64 if
neither does. A Keychain
prompt can still block it.

`auth token` needs a human. Never run it unattended.

**Tokens last about 22 hours (1 hour for auth-server tokens).** On exit 77,
stderr already contains the remedy. Show it verbatim.

### Writing

```bash
planbook lessons set --class-id 12345678 --date 09/03/2026 \
  --title "Photosynthesis" \
  --text "<p>Chloroplasts and the light reactions.</p>" \
  [--homework "Read ch. 4"] [--notes "Lab groups of 3"] [--dry-run]
```

`lessons set` is an **upsert keyed on class + date**. It reads first and carries
over anything you don't name.

A lesson has **six** sections. Check labels with `planbook lessons sections`.

Bulk writes:

```bash
planbook lessons bulk lessons.json [--class-id N] [--keep-going] [--dry-run]
```

### Destructive commands

Confirm with the user before running any of these:

- `classes delete --class-id N --yes` — removes the class **and every lesson in it**
- `lessons delete --class-id N --date D`
- `events delete --event-id N` — removes the **whole series** by default; `--occurrence-only` deletes only the occurrence the event record points at
- `events create --no-school` — permanently deletes every lesson on that date, or across `--date`…`--end-date`. The CLI refuses if lessons already exist; `--force` deletes them.
- `units delete --unit-id N --class-id N`
- `todos delete --todo-id N`
- `students delete --student-id N`

`classes delete` is the only one that requires `--yes`. The rest act immediately.

### Limitations

- `grades` and `attendance` are read-only.
- Seating charts, lesson banks, messages, and reporting are not mapped.
- `filterNotes` is blocked on an unknown parameter.
- Signing in needs a human at the keyboard: `auth browser`, `auth login`, `auth token`. `auth status` and `auth import` then run unattended.

## Safety

- Don't read, print, or edit `.env`, private keys, or credential files unless the user confirms.
