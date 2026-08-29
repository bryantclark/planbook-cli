# Planbook private API — recon notes

Reverse-engineered 2026-08-28 from a live session. Undocumented; can change without notice.

## Hosts

| host | what it is |
|---|---|
| `app.planbook.com` | Vue SPA. **Behind AWS WAF** — returns a "Human Verification" challenge (HTTP 405) to any non-browser client, including static `/js/*` assets. Do not script this host. |
| `api.planbook.com` | **The API. No WAF.** Plain curl works. Root path serves marketing HTML, which is why it looks like a dead end. |
| `auth.planbook.com` | Login. No WAF. SSO: Google, Microsoft, Clever, ClassLink, Apple. |

## Auth

**The credential is a JWT, not the `SESSION` cookie.**

The browser carries it as a cookie named `U|<view-id>|.accesstoken`. The server also
accepts it as `Authorization: Bearer <jwt>`, which is what this CLI sends - verified
working with no cookies at all.

`SESSION` is a decoy for anyone mapping this by hand: `api.planbook.com` issues one
to *unauthenticated* callers too, so DevTools shows a plausible `SESSION` next to the
real credential, and sending it alone returns `{"notLoggedIn":"true"}`.

Established by testing:

- `Authorization: Bearer <jwt>` alone authenticates. No cookie needed.
- The `<view-id>` in the cookie name is **not validated** - any non-empty value
  works - but the name must end in `.accesstoken`.
- The `x-pb-*` headers the web app sends are **not required**.
- The JWT payload has a double-encoded `sub`: a JSON *string* holding
  `{id, yearId, key, type, email, code, generic, legacy}`, plus a top-level `exp`.
- **Lifetime is about 22 hours.** No rotation on normal calls, and no refresh
  endpoint - `/refreshToken`, `/services/api/refresh-token`,
  `/services/api/token/refresh` and `/services/planbook/refreshToken` all 404.

`/services/api/*` endpoints additionally want an API key:
`{"notLoggedIn":"true","message":"Invalid API Key. Please contact planbook.com
administrator."}` - there is a sanctioned API-key mechanism worth asking
support@planbook.com about.

Note `/services/*` returns **HTTP 200 with `{"error":"true","message":"HTTP 404 Not
Found"}`** for unknown paths, so a 200 there proves nothing. Read the body.

Unauthenticated calls return `{"notLoggedIn":"true"}` with HTTP 200 - **check the
body, not the status code.**


## Conventions

- All calls are **POST**, `application/x-www-form-urlencoded`. No JSON bodies.
- Booleans are `Y` / `N` (not true/false), except `fetchDay` which is literal `true`.
- Absent integers are `0`, **never empty string** — empty triggers a server-side Java NPE:
  `Cannot invoke "java.lang.Integer.intValue()" because ... getInteger(String) is null`
- Dates are `MM/DD/YYYY`.
- Class records use abbreviated keys: `cId` class id, `cN` name, `cYId` year id,
  `mT`/`tT`/`wT`… day-teach flags, `mSt`/`mEt`… per-day start/end times.

## Endpoints observed

Read:
```
POST /getClasses2        -> {classes[], currentYearId, lessonBanks, districtLessonBanks}
POST /getSettings
POST /getStandards
POST /getLessonsEvents   (monday, userMode=T, fetchWeekSize)
POST /getSpecialDays     (teacherId, yearId, schoolId)
POST /getAssignments  /getAssessments  /getCommentsTo
POST /getAttachmentList  (teacherId, isFolderStructured, withAllFolders)
POST /services/planbook/template/get
POST /services/api/stickers
POST /services/api/referencedata/maintenanceData
POST /services/planbook/oneRosterClient/getAllRosteredItems
```

Write:
```
POST /addClass       ~40 fields: className, classStartDate, classEndDate, color,
                     mondayTeach..sundayTeach, wk2*Teach, useSchoolStart/End, ...
POST /updateLesson   25 fields (below)
```

## `/updateLesson` — the important one

**Addressed by `classId` + `customDate`. No lesson id required.** It is an idempotent
upsert: writing the same date twice updates in place, no duplicate. This is what CSV
import cannot do (CSV is append-only — "imported lessons appear after current lessons").

Verified payload:

```
classId=<int>            customDate=09/03/2026     unitId=0
extraLesson=0            lessonId=0                linkedLessonId=0
lessonTitle=<str>        lessonText=<html>
homeworkText=            notesText=
tab4Text=  tab5Text=  tab6Text=                   (custom lesson-layout tabs)
addClassDaysCode=        customStart=  customEnd=
lessonLock=N             isEditingALinkedLesson=N
strategySent=Y           unitStandardsSent=Y       statusesSent=Y
schoolWorks=[]           updatedFields=LESSONTEXT,LESSONTITLE
oldLesson=               fetchDay=true
```

Success = HTTP 200 with `error` absent. Failure = HTTP 200 with `{"error":"true","msg":...}`.

`updatedFields` is an uppercase comma list naming which fields you touched.

## Measured

- 164 ms per lesson, serial, from the browser.
- 5 lessons batch-written across a week: all landed on correct dates.
- Correctly skipped Labor Day (placed below the holiday marker) with no special handling.
- Re-write of an existing date updated in place — confirmed visually, no duplicate row.

## Open

- Headless form login against `auth.planbook.com` - untested (needs credentials, and the account here uses SSO).
  Fallback: paste a cookie periodically.
- Delete-class endpoint not captured (UI-driven cleanup only).
- CSV import column set still unconfirmed (sample file is behind a HubSpot bot-check).

## ToS

Terms (last updated 2020-07-01) contain **no** anti-scraping, anti-automation, or
reverse-engineering clause. Relevant: "No Resale of Service" (broad, aimed at resale);
no forging headers to disguise origin; they reserve rate limits; termination at sole
discretion for violating the "spirit" of the ToS. Risk is account termination, not legal.
Use an honest User-Agent, serialize requests, own account only.

## OAuth2 / OIDC (auth.planbook.com)

Planbook runs a Spring Authorization Server with full discovery at
`https://auth.planbook.com/.well-known/openid-configuration`:

```
authorization_endpoint         /oauth2/authorize
device_authorization_endpoint  /oauth2/device_authorization
token_endpoint                 /oauth2/token
jwks_uri                       /oauth2/jwks
userinfo_endpoint              /userinfo
grant_types_supported          authorization_code, client_credentials,
                               refresh_token, device_code
scopes_supported               openid
```

The device-code grant is advertised, which is the standard "open your default
browser and sign in" pattern used by CLIs like `glab` and `gh`.

**It is not usable by a CLI today, for two specific reasons:**

1. `token_endpoint_auth_methods_supported` lists only `client_secret_basic`,
   `client_secret_post`, `client_secret_jwt`, `private_key_jwt`. There is no
   `none`, so **public clients are not supported**. A CLI cannot hold a client
   secret safely.
2. `code_challenge_methods_supported` is absent, so **PKCE is not advertised** -
   the mechanism that lets a public client use the authorization-code flow safely.

Both `/oauth2/authorize` and `/oauth2/device_authorization` 302 to `/login` when
unauthenticated, so client validation cannot be probed from outside.

This server is evidently built for Planbook's confidential partner integrations,
not for third-party CLIs. `glab` can do browser sign-in because GitLab registered
a client id for it; the same is required here.

**Concrete ask for support@planbook.com:** register a public OAuth client for
command-line use, supporting either the device-code grant or authorization-code
with PKCE. The infrastructure already exists; only a client registration is
missing. Note also the issuer is advertised as `http://auth.planbook.com`
(not https), which is worth flagging to them.


## Times

Planbook stores times in 12-hour form only: `"9:00 AM"`. Verified by writing three
formats to `customStart` and reading them back:

| sent | stored |
|---|---|
| `09:00` (24-hour) | `""` - **silently dropped** |
| `9:00AM` | `9:00 AM` (normalized) |
| `9:00 AM` | `9:00 AM` |

A 24-hour string is accepted without any error and the time is lost. `parse_time()`
in `api.py` converts both forms before sending.

Three separate places carry times:

- `updateLesson` -> `customStart` / `customEnd`, overriding the class schedule for
  that one date.
- `addEvent` -> `eventStartTime` / `eventEndTime`.
- the class `schedules` JSON -> `startDayN` / `endDayN`, where N is Sunday-indexed.
  `getClass` echoes these back as `mondayStartTime`, `mondayEndTime`, and so on.


## Standards and assignments on a lesson

Both attach through `/updateLesson`, and both only stick to a lesson that already
exists - on a brand-new date `lessonId` is `0` and the server drops them silently.
The CLI writes the lesson first, re-reads its `lessonId`, then attaches.

**Standards** travel as `standardDBIds`, using the **`dbId`**, not the human id
like `3.NBT.A.1`. Verified semantics:

| sent | result |
|---|---|
| `standardDBIds=118071` | set becomes exactly `[118071]` - it replaces, not appends |
| `standardDBIds=118071,118072` | **clears the set** - a comma list is not parsed |
| repeated `standardDBIds=118071&standardDBIds=118072` | both attach |
| `standardDBIds=` | clears |

So it is a whole-set replace delivered as repeated form fields. A captured payload
looks like it sends only one id because duplicate keys collapse when you parse the
body into a dict - which is exactly the mistake that made this look like an append.

**Assignments** travel as `schoolWorks`, a JSON array:

```json
[{"type":"ASSIGNMENT","typeId":3865664,"shortValueText":"","longValueText":0}]
```

They come back on the lesson as `addendums`. An assignment belongs to one class
(`subjectId`); attaching one from another class is accepted and does nothing, so the
CLI checks ownership first and refuses.
