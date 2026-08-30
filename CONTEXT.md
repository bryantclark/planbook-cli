# Context

## What this project is

A CLI that wraps Planbook.com's private API so agents and people can read and write
lesson plans from the terminal. Planbook publishes no API and no CLI — this tool
reverse-engineered the endpoints the web app uses.

## Core entities

- **Class** — a course on a teacher's schedule. Has a date range, day-of-week schedule with per-day times, and many lessons.
- **Lesson** — one day's plan for one class. Keyed by class + date. Has six text sections, standards, assignments, and attachments.
- **Unit** — a grouping of lessons within a class. Belongs to a class.
- **Event** — a calendar entry (holiday, assembly). Can repeat. A no-school event permanently deletes lessons on that date.
- **Student** — belongs to a class. Has contact info and a photo URL.
- **To-do** — a task item. Has priority, due date, and repeat rules.
- **Standard** — a curriculum standard (e.g. "3.NBT.A.1"). Referenced by `db_id`, not the human identifier.
- **Assignment** — belongs to one class. Attached to lessons via `schoolWorks`.
- **Attachment** — a file uploaded to S3. Linked to lessons by signed URL.

## Relationships

```
Teacher
  └──< Class ──< Lesson ──< Standard
       │    └──< Unit         │──< Assignment
       │    └──< Student      └──< Attachment
       └──< Event
  └──< To-do
```

## Vocabulary that matters

- **Wire format** — the raw field names and conventions the server uses (`cId`, `Y`/`N` booleans, `MM/DD/YYYY` dates). Distinct from the CLI's readable output.

## Open questions

Tracked in [docs/API-NOTES.md](docs/API-NOTES.md) — see the "Open", "Blocked endpoints", and "OAuth2" sections.
