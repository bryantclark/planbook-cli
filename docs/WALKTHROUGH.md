# Planning a week with an assistant

What it looks like when a teacher plans a week in Planbook through an AI
assistant driving this CLI. Every command below is one the assistant runs; the
teacher only talks.

The teacher says:

> Plan next week's science for 4th grade. We're starting the unit on
> ecosystems. Use the district pacing guide I pasted. Keep Friday light,
> it's a half day.

## 1. Preflight

```bash
planbook check
```

```json
{"contract": "1.5", "authenticated": true, "expires_in_hours": 18.2,
 "current_year_id": 92491353,
 "classes": [{"id": 1370738, "name": "4th Grade Science",
              "start_date": "08/24/2026", "end_date": "06/04/2027",
              "days": "MTWRF"}]}
```

One round trip tells the assistant the session works, how long it has, and
the real class id. On exit 77 it relays the sign-in instructions to the
teacher and stops. It never guesses at a token.

## 2. Look before writing

```bash
planbook lessons week --class-id 1370738 --date 09/14/2026
```

Returns the five days as they stand, so the assistant carries over anything
already there. A lesson has six sections; the labels come from
`planbook lessons sections`, so the assistant puts homework in the homework
box and not in the notes.

## 3. Draft, then preview

The assistant writes the week to a file and previews it:

```bash
planbook lessons bulk week.json --class-id 1370738 --dry-run
```

`--dry-run` prints the exact requests, per day, with `updated_fields` naming
what changes. Nothing is sent. The teacher can read the plan in Planbook's own
vocabulary before anything lands.

## 4. Write, resumably

```bash
planbook lessons bulk week.json --class-id 1370738 --journal week.jsonl
```

Each lesson is read back after it is written and compared to what was sent.
A server that answers 200 and stores nothing fails loudly. If the run is
interrupted, `--resume` finishes only what is missing.

```json
{"class_id": 1370738, "date": "09/14/2026", "updated_fields":
 ["title", "text", "homework"], "effects": {"standards": ["4-LS1-1"]}}
```

## 5. Fix one thing

> Actually, move the food web activity to Wednesday and make Tuesday the
> vocabulary day.

`lessons set` is an upsert keyed on class and date. It reads first and
carries over what is not named, so swapping two days touches two records and
nothing else.

## What the teacher never did

- Open a terminal.
- Copy a lesson from a chat window into a text box.
- Retype standards codes.
- Wonder whether the write landed.

## What the assistant never did

- Guess at a class id or a date format.
- Send HTML through a shell. `-` reads any text flag from stdin.
- Delete something without `--yes` and a `cascade` count in front of it.
- Retry a write the CLI said not to retry.

## The catch

The token behind all of this is a full-account session copied out of the
teacher's browser. It has no scopes, no consent screen, and no revoke button,
and it expires every day. That is why this works for one household and cannot
be handed to a school. [PRODUCTION-READINESS.md](PRODUCTION-READINESS.md) is
what would fix it.
