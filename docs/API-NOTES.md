# Planbook API notes

Mapped 2026-08-28 from the web app's network traffic. No published API docs
exist; endpoints can change without notice.

## Hosts

| host | notes |
|---|---|
| `app.planbook.com` | Vue SPA. Returns 405 to non-browser clients. Not scripted by this tool. |
| `api.planbook.com` | The API. Root path serves marketing HTML — looks like a dead end but isn't. |
| `auth.planbook.com` | Login. SSO: Google, Microsoft, Clever, ClassLink, Apple. |

Edge protection is not uniform across these hosts. Details went to Planbook
directly; see [PRODUCTION-READINESS.md](PRODUCTION-READINESS.md).

## Auth

**The credential is a JWT, not the `SESSION` cookie.**

The browser carries it as `U|<view-id>|.accesstoken`. The server also accepts
`Authorization: Bearer <jwt>` with no cookies.

`SESSION` is a decoy: `api.planbook.com` issues one to unauthenticated callers
too. Sending it alone returns `{"notLoggedIn":"true"}`.

Established by testing:

- `Authorization: Bearer <jwt>` alone authenticates.
- The `<view-id>` in the cookie name is not validated — any non-empty value works — but the name must end in `.accesstoken`.
- The `x-pb-*` headers the web app sends are not required.
- **Two issuers, different identity shapes.** The older payload double-encodes: `sub` is a JSON string with `{id, yearId, key, type, email, code, generic, legacy}`. Auth-server tokens put the same data under `https://planbook.com/claims` and spell the year `yearid` (lowercase d). `token.identity()` flattens both.
- Auth-server tokens live **1 hour**; legacy tokens live **~22 hours**.
- No refresh endpoint. Tested `/refreshToken`, `/services/api/refresh-token`, `/services/api/token/refresh`, `/services/planbook/refreshToken` — all 404.

`/services/api/*` endpoints want an API key:
`{"notLoggedIn":"true","message":"Invalid API Key. Please contact planbook.com administrator."}`

`/services/*` returns **HTTP 200 with `{"error":"true","message":"HTTP 404 Not Found"}`** for
unknown paths. A 200 proves nothing. Read the body.

## Conventions

- Most calls are **POST**, `application/x-www-form-urlencoded`. Exceptions: GET-only `/services/planbook/**` and a few JSON-body endpoints (see "Two request styles" below).
- Booleans are `Y`/`N` on class day-teach flags and lesson flags. Event and class *control* fields are literal `true`/`false`: `noSchool`, `noCycle`, `privateFlag`, `verifyShift`, `scheduleChange`. `fetchDay` on `/updateLesson` is literal `true` too.
- `shiftLessons` is the exception to the exception: `N` on `/addEvent`, `false` on `/deleteEvent` and the class endpoints. A wrong value is a silent no-op.
- Absent integers: `0`, never `""` (empty triggers a Java NPE).
- Dates: `MM/DD/YYYY`.
- Abbreviated class keys: `cId`, `cN`, `cYId`, `mT`/`tT`/`wT` (teach flags), `mSt`/`mEt` (times).
- `scheduleChange=true` is required when updating a class, or the rename lands and the new schedule is silently discarded.
- `verifyShift=true` means check, don't commit. Events and classes answer exactly like success and write nothing. Commit with `false`.
- `teachDay1` is **Sunday**, not Monday, in the class schedule JSON.
- `subjectId` is the class id on the unit endpoints, on assignment records, and on `/getStudentScoresServlet`.

`raw` applies none of these for you.

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
POST /addClass       ~40 fields
POST /updateLesson   25 fields (below)
```

## `/updateLesson`

Addressed by `classId` + `customDate`. No lesson id required. Idempotent upsert.

Verified payload:

```
classId=<int>            customDate=09/03/2026     unitId=0
extraLesson=0            lessonId=0                linkedLessonId=0
lessonTitle=<str>        lessonText=<html>
homeworkText=            notesText=
tab4Text=  tab5Text=  tab6Text=                   (custom tabs)
addClassDaysCode=        customStart=  customEnd=
lessonLock=N             isEditingALinkedLesson=N
strategySent=Y           unitStandardsSent=Y       statusesSent=Y
schoolWorks=[]           updatedFields=LESSONTEXT,LESSONTITLE
oldLesson=               fetchDay=true
```

Success: HTTP 200, `error` absent. Failure: HTTP 200, `{"error":"true","msg":...}`.

## Full-replace gotcha

See [read-before-write decision](../decisions/2026-08-28-read-before-write.md). Fields lost before carry-over was added:

| endpoint | field | result of omitting it |
|---|---|---|
| `/updateLesson` | `lessonText`, `homeworkText`, `notesText` | emptied |
| `/updateLesson` | `schoolWorks` | `[]` — detached all assignments |
| `/updateLesson` | `unitId`, `lessonLock`, `extraLesson`, `linkedLessonId` | reset to defaults |
| `/updateToDo` | `priority`, `done`, `dueDate`, `repeats` | reopened at low priority |
| `/updateClass/v10` | `classDesc`, `color`, `lessonLayoutId`, per-day times | wiped |
| `/updateUnit` | `unitDesc`, `unitStart`, `unitEnd`, `unitNum`, `unitTitle`, and the six section texts (`unitLessonText`, `unitHomeworkText`, `unitNotesText`, `unitSection4Text`–`unitSection6Text`) | emptied |
| `/updateStudentServlet` | email, phone, parent email, code, birthdate, middle name, `studentPhotoUrl` | emptied |

## Standards and assignments on a lesson

Both go through `/updateLesson` and only stick to a lesson that already exists —
on a new date (`lessonId=0`) the server drops them silently. The CLI writes the
lesson first, re-reads its `lessonId`, then attaches.

**Standards** use `standardDBIds` with the **`dbId`**, not the human id:

| sent | result |
|---|---|
| `standardDBIds=118071` | set = exactly `[118071]` (replaces, not appends) |
| `standardDBIds=118071,118072` | **clears** — comma list isn't parsed |
| repeated `standardDBIds=118071&standardDBIds=118072` | both attach |
| `standardDBIds=` | clears |

**Assignments** use `schoolWorks`, a JSON array. An assignment belongs to one
class (`subjectId`); attaching one from another class is accepted and does
nothing — the CLI checks ownership first.

```json
[{"type":"ASSIGNMENT","typeId":3865664,"shortValueText":"","longValueText":0}]
```

## Attachments

Upload is multipart:

```
POST /uploadAttachment    multipart, one file part (any field name)
  -> {"fileName": "...", "fileURL": "https://s3.amazonaws.com/PlanbookAttachments/..."}
```

The part **must carry a content type** or the server throws an NPE.

The lesson stores the **signed URL**, not a reference to the resource. Re-uploading
a file under the same name silently replaces its content in every lesson linked to it.

Linking to a lesson goes through `/updateLesson` as repeated triples:

```
attachmentNames=file.txt   attachmentURL=https://s3/...   attachmentPrivate=N
```

## No-school days destroy lessons

Creating an event with `noSchool=true` **permanently deletes every lesson on that
date**. Deleting the event restores the empty slots but not the lessons. The CLI
checks for existing lessons first and refuses without `events create --force`.

## Times

Planbook stores 12-hour only. A 24-hour string is accepted without error and the
time is lost.

Three places carry times:
- `updateLesson` `customStart`/`customEnd` — **do nothing**. Accepted, stored, ignored on read-back. Spellings tried: `CUSTOMSTART`/`CUSTOMEND`, `CUSTOMTIME` in `updatedFields`, `extraLesson=1`, `lessonStart`, `startTime`, `lessonStartTime`, `customStartTime`, `periodStart`, `timeStart`. All read back unchanged.
- `addEvent` `eventStartTime`/`eventEndTime` — works.
- Class `schedules` `startDayN`/`endDayN` (Sunday-indexed).

## getLessonsEvents

`days` list, one entry per day. Lessons carry no date — the date comes from the
day they sit in. Events appear with `"type": "E"`.

## Two request styles

`/xxxServlet` and bare `/getX`/`/addX` are form-encoded POST.
`/services/planbook/**` is a Spring layer:

| response | meaning |
|---|---|
| 405 to POST | endpoint is GET |
| 415 to JSON POST | wants form encoding |
| 200 with `{"error":"true","message":"HTTP 404 Not Found"}` | no such path |
| HTML page | SPA fallback: wrong path or method |

GET endpoints:
```
GET /services/planbook/attendance/get?classId=&date=
GET /services/planbook/attendance/getLessonsByDate?date=
```

## Endpoint map

| feature | endpoints |
|---|---|
| students | `/addStudentServlet`, `/updateStudentServlet`, `/deleteStudentServlet` (POST), `/getStudentsServlet` (POST, needs `classId`+`userMode`), `/services/planbook/student/getAllFromSchool` |
| attendance | `/services/planbook/attendance/get`, `.../getLessonsByDate` (GET) |
| grades | `/getStudentScoresServlet` (POST, needs `classId`+subject), `/services/planbook/student/studentsTagged` |
| templates | `/services/planbook/template/get` (GET), `/addTemplate`, `/updateTemplate`, `/deleteTemplate` |
| lesson banks | no own endpoints — reuses `/getLessonsEvents` and `/getUnits` |
| lesson moves | `/bumpLesson`, `/extendLesson` (blocked on unknown param) |

## Blocked endpoints

| endpoint | blocker |
|---|---|
| `/services/planbook/newNote/filterNotes` | unnamed Long |
| `/bumpLesson` | unnamed Integer |
| `/extendLesson` | unnamed Integer |
| `/getStandardsReport` | unnamed int; exhaustive probing failed |

One captured browser request would settle each.

## OAuth2 / OIDC (auth.planbook.com)

Spring Authorization Server. Device-code grant is advertised but **not usable by
a CLI**:

1. No `none` in `token_endpoint_auth_methods_supported` — no public clients.
2. No `code_challenge_methods_supported` — no PKCE.

Ask support@planbook.com about registering a public OAuth client. Issuer is
`http` (not `https`).

## ToS

Terms (2020-07-01) have **no** anti-scraping, anti-automation, or
reverse-engineering clause. They forbid forging headers, reserve rate limits, and
allow discretionary termination. Risk is account termination, not legal.
**Use your own account only.**

## Open

- Headless form login against `auth.planbook.com` — untested; account uses SSO.
- CSV import columns unconfirmed (sample file behind a HubSpot bot-check).
- Carry-over field names for `units update` (`unitDesc`, `unitStart`, `unitEnd`,
  the six section texts) and `students update` (`phoneNumber`,
  `parentEmailAddress`, `birthDate`) are inferred and tested only against mocks.
  A wrong spelling blanks the field on every update. Confirm against a live read.
