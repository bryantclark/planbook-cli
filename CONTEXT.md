# Context

## What this project is

A CLI that wraps Planbook.com's private API so agents and people can read and write
lesson plans from the terminal. No published API exists yet — this tool was built
against the endpoints the web app uses.

## Core entities

- **Class** — a course on a teacher's schedule. Has a date range, day-of-week schedule with per-day times, and many lessons.
- **Lesson** — one day's plan for one class. Keyed by class + date. Has six text sections, standards, assignments, and attachments.
- **Unit** — a grouping of lessons within a class. Belongs to a class.
- **Event** — an account-level calendar entry (holiday, assembly), not scoped to a class. Can repeat. A no-school event permanently deletes lessons on that date.
- **Student** — an account-level record, enrolled in classes. Has contact info and a photo URL. A full record reads only through a class (`--class-id`).
- **To-do** — a task item. Has priority, due date, and repeat rules.
- **Standard** — a curriculum standard (e.g. "3.NBT.A.1"). Referenced by `db_id`, not the human identifier.
- **Assignment** — belongs to one class. Attached to lessons via `schoolWorks`.
- **Attachment** — a file uploaded to S3. Linked to lessons by signed URL.

## Relationships

```
Teacher
  ├──< Class
  │      ├──< Lesson
  │      ├──< Unit
  │      └──< Assignment ──> Lesson (via schoolWorks)
  ├──< Student >──< Class
  ├──< Standard >──< Lesson
  ├──< Attachment >──< Lesson
  ├──< Event
  └──< To-do
```

`>──<` is many-to-many. Standards and attachments are account-level and shared;
re-uploading an attachment changes it in every lesson linked to it.

## Vocabulary that matters

- **Wire format** — the raw field names and conventions the server uses (`cId`, `Y`/`N` booleans, `MM/DD/YYYY` dates). Distinct from the CLI's readable output.

## Open questions

Tracked in [docs/API-NOTES.md](docs/API-NOTES.md) — see the "Open", "Blocked endpoints", and "OAuth2" sections.
