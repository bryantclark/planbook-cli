# Planbook private API — recon notes

Reverse-engineered 2026-08-28 from a live session. Undocumented; can change without notice.

## Hosts

| host | what it is |
|---|---|
| `app.planbook.com` | Vue SPA. **Behind AWS WAF** — returns a "Human Verification" challenge (HTTP 405) to any non-browser client, including static `/js/*` assets. Do not script this host. |
| `api.planbook.com` | **The API. No WAF.** Plain curl works. Root path serves marketing HTML, which is why it looks like a dead end. |
| `auth.planbook.com` | Login. No WAF. SSO: Google, Microsoft, Clever, ClassLink, Apple. |

## Auth

Single `SESSION` cookie (HttpOnly, UUID). Unauthenticated calls return `{"notLoggedIn":"true"}` with HTTP 200 — **check the body, not the status code.**

`/services/api/*` endpoints additionally want an API key:
`{"notLoggedIn":"true","message":"Invalid API Key. Please contact planbook.com administrator."}`
→ There is a sanctioned API-key mechanism. Worth asking support@planbook.com about before building on this.

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

- Headless login against `auth.planbook.com` to obtain `SESSION` — untested (needs credentials).
  Fallback: paste a cookie periodically.
- Delete-class endpoint not captured (UI-driven cleanup only).
- CSV import column set still unconfirmed (sample file is behind a HubSpot bot-check).

## ToS

Terms (last updated 2020-07-01) contain **no** anti-scraping, anti-automation, or
reverse-engineering clause. Relevant: "No Resale of Service" (broad, aimed at resale);
no forging headers to disguise origin; they reserve rate limits; termination at sole
discretion for violating the "spirit" of the ToS. Risk is account termination, not legal.
Use an honest User-Agent, serialize requests, own account only.
