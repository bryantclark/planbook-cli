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
planbook check
```

One round trip answers all three things every later command needs: whether the
session works, how many hours of token are left, and the real class ids.

- **Exit 0** — signed in. Output carries the account, `expires_in_hours`,
  `current_year_id` and a `classes` list of `{id, name, start_date, end_date, days}`.
- **Exit 77** — not signed in. Stderr contains the sign-in URL and exact command.
  Relay it to the user verbatim and stop.

`planbook auth status` still works and reports the same session facts without
the class list.

### Learn the surface in one call

```bash
planbook schema
```

Every command, flag, type, default, and error kind as JSON, generated from the
parser. Read this instead of running `--help` per group. It reports the
contract version; branch on `contract` if you cache what you learned.

### Output contract

- **stdout** is JSON on success, empty on failure. Exception: `lessons bulk` prints per-item results and exits 1 when any item failed.
- **stderr** is prose diagnostics by default. Never parse the prose.
- **`--error-json`** (or `PLANBOOK_ERROR_JSON=1`) replaces the prose with one
  JSON object, which is what an agent should use:

  ```json
  {"error": {"contract": "1.5", "kind": "SchemaDrift", "code": 65,
             "retryable": false, "message": "...", "remedy": "...",
             "details": {}}}
  ```

  `kind` is stable, `retryable` says whether running it again could work, and
  `remedy` says what to do. `planbook schema` lists every kind.
- **`updated_fields`** appears on every write result and every `--dry-run`
  preview: the fields you named, in the same snake_case vocabulary the lists
  use (`start_date`, not `start`). Every one was read back and checked. A
  create names nothing, so the list is empty there.
- **`cascade`** appears only when a write destroys records you did not name.
  It counts them, so `--dry-run` shows the blast radius before you commit.
- **`effects`** appears only when a write did something beyond the fields you
  named, so its absence is the signal that nothing else happened:

  | key | on | meaning |
  |---|---|---|
  | `standards`, `assignments`, `attachments` | `lessons set` | what the lesson now links to |
  | `attachments_pending` | `lessons set` | files uploaded but not yet linked |
  | `scope` | `events delete` | `series` or `occurrence` |
  | `replaces_existing` | `attachments upload` | names that overwrote a stored file in every lesson linked to it, or `null` when the lookup failed |

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

- **stdin:** pass `-` to any text flag (`--text`, `--notes`, `--homework`,
  `--title`, `--section KEY=-`) and to `lessons bulk -` to read that value from
  stdin. Use it for HTML — quoting markup through a shell is where calls get
  mangled. One `-` per invocation.
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
| `schema` | the whole command surface as JSON |
| `check` | preflight: session, hours left, class ids |

Every `create` returns the new record's id as **`id`**, and never `null`. The
create endpoints do not report an id, so it is recovered by diffing the list
around the write and then narrowing by the fields just written. Add `--id-only`
to get `{"id": N}` and nothing else. If the id genuinely cannot be proven — two
identical records appearing at once — the command fails with `kind:
"Ambiguous"`, whose remedy says the record exists and you must not retry.

Every write is read back and compared against the fields you named, so a
server that answers HTTP 200 and stores nothing fails with `kind:
"PostconditionFailed"`. If the read-back itself fails, the write already
landed: that is `kind: "Ambiguous"`, and its remedy says not to retry. Three
are unverified: `students delete` without `--class-id` (there is no get-one
endpoint to read back), `attachments upload`, and `raw`, which cannot know what
it just sent.

`students update` needs `--class-id` as well as `--student-id`. `units update`
and `units delete` need the class the unit is in, and refuse (exit 64) if it is
another one.

**Every record answers to `id`** — every list, and every `create` result.
`classes`, `students`, `units`, `todos`, `events` and `templates` all use the
same readable field names. Where a command has `--raw` it returns the untouched
wire body; `planbook schema` lists which ones do.

### Authentication

`auth status` and `auth import` are safe unattended. `auth import` may raise a
macOS Keychain prompt. Without a TTY it never waits for you to sign in: it
succeeds if a browser or the stored session holds a usable token, and exits 64
if neither does. A Keychain prompt can still block it.

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
planbook lessons bulk lessons.json [--class-id N] [--keep-going] [--dry-run] [--journal run.jsonl] [--resume]
```

`--journal` records every item as it lands, keyed by class + date and hashed on
content. `--resume` then reruns only what is missing — an interrupted run is
picked up without duplicating or skipping a lesson. Editing an item in the file
changes its hash, so it is written again rather than skipped.

### Destructive commands

One policy, applied to all of them:

- **Every** destructive command takes `--dry-run`, which sends no write and
  reports the exact requests plus a `cascade` count of what else would go. It
  still reads: a preview built without the current record would show this write
  blanking fields the real one carries over, so `--dry-run` needs a session.
- **`--yes` is required** when the delete destroys records you did not name.
  Without it the command exits 64 and names the blast radius. The flag exists
  only on those commands; the rest of the table below does not accept one.

Confirm with the user before running any of these:

| command | cascade | needs `--yes` |
|---|---|---|
| `classes delete --class-id N` | every lesson in the class | always |
| `events delete --event-id N` | the whole repeating series | when the series has more than one date |
| `events create --no-school` | every lesson in the date range | when lessons exist |
| `lessons delete --class-id N --date D` | — | no |
| `units delete --unit-id N --class-id N` | — | no |
| `todos delete --todo-id N` | — | no |
| `students delete --student-id N` | — | no |

`events delete --occurrence-only` drops one date and needs no confirmation.

### Limitations

- `grades` and `attendance` are read-only.
- Seating charts, lesson banks, messages, and reporting are not mapped.
- `filterNotes` is blocked on an unknown parameter.
- Every write costs an extra read: read-before-write, then a read-back to prove
  it landed. Budget three requests per lesson in a bulk run.
- Signing in needs a human at the keyboard: `auth token`, and the Keychain prompt behind `auth import`. `auth status` then runs unattended.

## Safety

- Don't read, print, or edit `.env`, private keys, or credential files unless the user confirms.
