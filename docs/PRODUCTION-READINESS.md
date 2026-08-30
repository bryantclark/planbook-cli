# What it would take to make this official

Written for Planbook. This tool works and people can use it today, but it is
unofficial, and a few things have to change before Planbook could put its name
on it or market it. This file says what those things are, who has to do each
one, and roughly how big it is.

Contact: through GitHub — github.com/bryantclark/planbook-cli.

## Where it stands today

| | |
|---|---|
| Licence | MIT, source public at github.com/bryantclark/planbook-cli |
| Published | PyPI, `planbook-cli`, released from CI with a trusted publisher |
| Coverage | ~30 endpoints: classes, lessons, units, events, to-dos, students, grades, attendance, standards, assignments, attachments |
| Users | One teacher, daily, through an AI assistant. That is the whole user base. |
| Built against | The private API the web app uses, mapped by watching a signed-in session's own traffic. No published API exists. |
| Tests / CI | Unit tests with mocked HTTP, lint, type-check, all gates enforced on every push |

The domain knowledge is the asset, not the code. `docs/API-NOTES.md` is a
written-down model of the API's conventions and traps — full-record replace on
update, `Y`/`N` booleans, `0` for absent integers, which fields silently vanish
if omitted. Most of a client SDK's spec is already there.

## The blocker: authentication

Today the CLI gets its credential one of two ways: it reads the
`.accesstoken` JWT out of the browser cookie store of a browser the teacher is
already signed in to, or the teacher pastes one in by hand. Both send it as
`Authorization: Bearer`. The token is stored at `~/.config/planbook/token.json`,
mode 0600, and it expires on its own in about 22 hours.

That is a stopgap and it should not be how an official integration works. It
normalises teachers handing a live full-account session token to a program they
installed from a package index — and those accounts hold student names, grades,
and attendance. It also has no scopes, no consent screen, no revocation, and no
audit trail. There is no version of that which is production ready.

The replacement is mostly already built on Planbook's side.
`auth.planbook.com` runs a Spring Authorization Server publishing OIDC
discovery. What its metadata does not advertise:

- `none` in `token_endpoint_auth_methods_supported`. Without it there are no
  public clients, and a CLI distributed on PyPI cannot hold a client secret.
- `code_challenge_methods_supported`. No PKCE, so the authorization-code flow
  has no safe form for a public client.
- A refresh grant reachable by that client. There is no refresh endpoint on the
  private API either — every session ends when the token does.

Also: the discovery document advertises its issuer over `http`, not `https`.
Conforming clients reject that outright.

**Planbook's side** — register a public client, enable PKCE (S256), allow the
loopback redirect (RFC 8252) and ideally the device-code grant, define a scope
vocabulary, put up a consent screen naming what a client can read and write,
and give teachers and district admins a page that lists and revokes connected
apps. Fix the issuer URL.

**This side** — swap browser-token import for that flow, handle refresh and the
new 401/403 shapes, update the error messages and docs. It is a small amount of
work and it is entirely downstream of the decisions above, which is why it is
not written yet: a flow no server accepts is not a feature.

## Decisions that come before the code

Auth is the implementation detail. These are the real questions, and they are
Planbook's to answer, not mine:

- Do third-party agents get write access to gradebooks at all, or read-only
  first?
- Scoped consent: per-class, per-capability, or one all-or-nothing grant?
- Do school and district admins get a policy switch over what their teachers
  can connect?
- Revocation and audit: when a district asks who wrote that grade, what answers?
- Rate limits and quotas per client, and what happens when one is hit.
- Support load. An agent that mangles someone's week generates a ticket to
  Planbook, not to the agent's author.

## Legal and compliance

- **FERPA / COPPA.** Students, grades, and attendance are education records. A
  vendor-blessed client that touches them has to fit the DPAs Planbook already
  signs with districts: audit logging, retention and deletion, and a defined
  processor role for anything downstream of the API. Today the tool prints
  student names and email addresses to a terminal, which is fine for a teacher
  reading their own roster and not fine as a shipped default without that
  posture written down.
- **Terms of service.** The current terms (2020-07-01) have no anti-automation,
  anti-scraping, or reverse-engineering clause. They forbid disguising the
  origin of a request — this tool sends an honest `User-Agent` naming itself
  and its repository — reserve rate limits, and allow discretionary
  termination. An official integration needs its own API terms: acceptable use,
  data handling, and a way to cut off a misbehaving client.
- **Trademark.** Current use is nominative and the README says "unofficial"
  in the first line. If Planbook adopts it, that changes either way: a name
  licence, or a rename and a fork under Planbook's own account.
- **Copyright.** MIT already lets Planbook use, modify, and ship this,
  including in a closed product. It does not transfer ownership. Making it an
  official client wants either an assignment or a CLA so there is one owner of
  record.
- **The API notes.** `docs/API-NOTES.md` documents the private API. It was
  written from the author's own account's traffic and contains no credentials
  or anyone else's data, but it is public documentation of an unpublished
  interface. Three ways that goes: it becomes the seed of Planbook's own
  developer docs, it moves to a private repository, or it comes down. Say
  which and it happens.

## Things worth fixing regardless

These were found while building and are reported here in general terms; details
have gone to Planbook directly rather than into a public file.

- The edge configuration differs between hosts, in a way that makes the
  protection on one of them easy to sidestep. Worth a look by whoever owns the
  WAF rules.
- The OIDC issuer URL is `http`.
- Long-lived tokens with no refresh and no revocation path. Shorter tokens plus
  refresh is strictly better than 22-hour bearer tokens with no way to kill one.
- Not security, but a data-loss bug: creating an event with `noSchool=true`
  permanently deletes every lesson on that date, and deleting the event does not
  bring them back. This CLI warns before doing it. The web app should too.

## What to build

Four phases. Phase 1 is Planbook's, and everything else waits on it.

### Phase 1 — Planbook enables third-party clients (Planbook, server-side)

| | |
|---|---|
| Register a public OAuth client | `token_endpoint_auth_methods_supported` gains `none` |
| Enable PKCE | `code_challenge_methods_supported: ["S256"]` |
| Allow loopback redirects | RFC 8252: `http://127.0.0.1:<any port>/…`, port not part of the registered value |
| Enable the refresh grant | so a session outlives one token |
| Optional but wanted | device-code grant, for machines with no browser |
| Fix the issuer | it is advertised as `http`, which conforming clients reject |
| Define scopes | see below |
| Consent screen | names the client and what it may read and write |
| Connected-apps page | teacher-level, and district-admin-level, with revoke |

A starting scope vocabulary, matching what the API already separates:

```
planbook.classes.read      planbook.classes.write
planbook.lessons.read      planbook.lessons.write
planbook.units.read        planbook.units.write
planbook.events.read       planbook.events.write
planbook.todos.read        planbook.todos.write
planbook.students.read     planbook.students.write
planbook.grades.read       planbook.attendance.read
```

Read and write split per resource, students and grades separable from
everything else, and no scope that grants the whole account. A first release
could ship read-only scopes and the lesson/unit/event writes, and hold back
student and grade writes entirely.

### Phase 2 — The client switches to it (this repo)

- Authorization code + PKCE with a loopback listener; device code as the
  fallback.
- Refresh handling: renew in the background, fail cleanly when the refresh
  token is revoked.
- New failure modes: insufficient scope, revoked grant, rate limited — each
  with an exit code and a message that says what to do.
- Delete `auth import`, `auth token`, `auth login`, and `auth browser`, and the
  browser-cookie dependency with them. This is the point of the whole exercise:
  no tool should be reading a teacher's cookie store.
- Migration: one release where both work and the old paths warn, then a release
  where only OAuth does.

### Phase 3 — What makes it marketable (joint)

- **Public API docs.** `docs/API-NOTES.md` is most of the raw material; it
  needs to become a documented, supported surface with stable field names
  rather than the wire format's `cId` and `Y`/`N`.
- **Rate limits and quotas**, published, per client, with a documented
  429 response.
- **Audit trail.** Every write records which client made it, so "who wrote that
  grade" has an answer.
- **Admin controls.** A school or district switch over whether teachers may
  connect third-party clients at all, and which ones.
- **Data-handling statement** covering third-party clients, fitting the
  district DPAs Planbook already signs.
- **A listing.** "Works with your AI assistant" is the marketable claim, and it
  needs a page on planbook.com, an install command, and a supported-integration
  badge to be real.

### Phase 4 — Handover

- Repo transferred or forked under Planbook's account, with copyright assigned
  or a CLA signed.
- Release pipeline and PyPI package name moved.
- Support path documented: what goes to Planbook, what stays with the client.

The client-side work in phases 2 and 4 is small — roughly two to four weeks of
one engineer, and about half of that is waiting. Phases 1 and 3 are the real
project, and they are Planbook's.

## What Planbook could do with it

Pick whichever fits; the first two both end with teachers able to use this
safely.

1. **Take it.** MIT already permits this. Register the public client, and
   either fork the repo or let it keep living here as a community client. No
   money changes hands. This is a fine outcome.
2. **Contract the finish.** Scope and price agreed up front: the OAuth client
   work, developer docs, error handling for the new failure modes, and a
   handover. Roughly two to four weeks of one engineer, about half of it
   waiting on the server-side work above.
3. **Do nothing.** The tool keeps working as long as the private API does. If
   the choice is between blocking it and leaving it alone, leaving it alone
   costs Planbook nothing and keeps a teacher productive — but it leaves the
   auth pattern in place, which is the part nobody should want.

Whatever the answer on the business side, the security items above stand on
their own and are worth routing internally today.
