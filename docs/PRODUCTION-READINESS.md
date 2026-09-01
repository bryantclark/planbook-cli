# What it would take to make this official

This tool works today, and I'd love for you to play with it to see why it's
useful. It isn't production-ready — primarily because of how it handles
authentication. Below is what I think it would take to turn this into a
first-rate tool that teachers would want.

## The short version

1. **Take the repo private.** The public repo documents an unpublished API.
   That's useful for evaluation but shouldn't stay public long-term. Access
   moves to Planbook directly.
2. **Planbook enables third-party auth.** Public OAuth client, PKCE, scopes,
   consent screen, token refresh, connected-apps page. Everything else is
   blocked on this.
3. **Pick a surface.** A CLI, an MCP server, or both from a shared library.
4. **Ship it safely.** Rate limits, audit trail, admin controls, FERPA-ready
   data handling, public API docs.

I'm happy to help with these for a fair price, but in case you want to do it
all internally, here is some free consulting on what I'd be thinking about.

## Why teachers want this

Teachers are trying to save time with AI. One of the main sources of mindless
busywork for teachers is moving data around between all their tools. Because
of that I think teachers will gravitate toward one general-purpose agent
— through programs
like [Claude for Teachers](https://www.anthropic.com/news/claude-for-teachers)
or [ChatGPT for Teachers](https://help.openai.com/en/articles/12844995-chatgpt-for-teachers)
— and connect it to all their tools so it can make edits and move data across
them. "Plan my week" is more valuable when the agent can read the standards
doc, draft the lessons, *and* put them on the calendar without the teacher
copying anything by hand.

I built this tool for my wife, an elementary teacher. It already saves her
lots of time. I'm sure thousands of other Planbook teachers would
want the same thing.


## Where it stands today

| | |
|---|---|
| Licence | MIT, source public at github.com/bryantclark/planbook-cli |
| Published | PyPI, `planbook-cli`, released from CI with a trusted publisher |
| Coverage | ~30 endpoints: classes, lessons, units, events, to-dos, students, grades, attendance, standards, assignments, attachments |
| Users | One teacher, daily, through an AI assistant |
| Built against | The private web-app API, mapped by observing a signed-in session's own traffic |
| Tests / CI | Unit tests with mocked HTTP, lint, type-check — all gates enforced on every push, with actions pinned to commit SHAs |
| Live validation | One account, one teacher. `PLANBOOK_LIVE=1 pytest tests/test_contract_live.py` reads that account and checks every projection against real responses; it is opt-in and off in CI, so drift is caught only when somebody runs it |

`docs/API-NOTES.md` documents the API's conventions and traps — full-record
replace on update, `Y`/`N` booleans, `0` for absent integers, fields that
vanish silently if omitted. Most of a client SDK's spec is already there.

## The blocker: authentication

The CLI reads the `.accesstoken` JWT from a browser cookie store or accepts
one pasted by hand. The token is stored at `~/.config/planbook/token.json`
(mode 0600) and expires in about 22 hours. See
[decisions/2026-08-30-one-auth-path.md](../decisions/2026-08-30-one-auth-path.md)
for why there is only this one path.

This is a stopgap. It puts a full-account session token into a program from a
package index — and those accounts hold student names, grades, and attendance.
No scopes, no consent screen, no revocation, no audit trail.

### What Planbook needs to enable

`auth.planbook.com` already runs a
[Spring Authorization Server](https://spring.io/projects/spring-authorization-server)
with OIDC discovery. What its metadata does not yet advertise:

- `none` in `token_endpoint_auth_methods_supported` — without it, no public
  clients. A CLI on PyPI can't hold a client secret.
- `code_challenge_methods_supported` — without
  [PKCE](https://oauth.net/2/pkce/), the authorization-code flow has no safe
  form for a public client.
- A refresh grant — every session ends when the token does.
- The issuer URL is `http`, not `https`. Conforming clients reject that.

Both proposals below need these server-side changes:

| | |
|---|---|
| Register a public OAuth client | `token_endpoint_auth_methods_supported` gains `none` |
| Enable PKCE | `code_challenge_methods_supported: ["S256"]` |
| Allow loopback redirects | [RFC 8252](https://datatracker.ietf.org/doc/html/rfc8252): `http://127.0.0.1:<any port>/…` |
| Enable the refresh grant | so a session outlives one token |
| Optional but wanted | [device-code grant](https://oauth.net/2/device-authorization-grant/) for machines with no browser |
| Fix the issuer URL | `https`, not `http` |
| Define scopes | see below |
| Consent screen | names the client and what it may read and write |
| Connected-apps page | teacher-level and district-admin-level, with revoke |

A starting scope vocabulary matching what the API already separates:

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
everything else. A first release could ship read-only scopes and the
lesson/unit/event writes, holding back student and grade writes entirely.

### Questions for Planbook

These are Planbook's decisions. The positions below are a starting point, not
conclusions:

- Do third-party agents get write access to gradebooks, or read-only first?
- Scoped consent: per-class, per-capability, or all-or-nothing?
- Do school and district admins get a policy switch over connected apps?
- When a district asks who wrote a grade, what answers?
- Rate limits per client, and what happens when one is hit.
- An agent that mangles someone's week generates a ticket to Planbook, not
  the agent's author. How does support handle that?

### Beyond auth

- **Public API docs.** `docs/API-NOTES.md` is most of the raw material; it
  needs stable field names rather than `cId` and `Y`/`N`.
- **Rate limits and quotas**, published, per client, with a documented 429.
- **Audit trail.** Every write records which client made it.
- **Admin controls.** A school or district switch over connected apps.
- **Data-handling statement** covering third-party clients and fitting existing
  district DPAs.

## Legal and compliance

- **FERPA / COPPA.** Students, grades, and attendance are education records.
  A vendor-blessed client has to fit the DPAs Planbook already signs with
  districts: audit logging, retention and deletion, and a defined processor
  role for anything downstream of the API.
- **Terms of service.** The current terms have no anti-automation clause. An
  official integration needs its own API terms: acceptable use, data handling,
  and a way to cut off a misbehaving client.
- **Trademark.** Current use is nominative and the README says "unofficial."
  If Planbook adopts it, that changes: either a name licence or a rename.
- **Copyright.** MIT lets Planbook use, modify, and ship this. Making it an
  official client needs either an assignment or a CLA so there is one owner.
- **The API notes.** `docs/API-NOTES.md` is public documentation of an
  unpublished interface. It either seeds Planbook's own developer docs, moves
  to a private repo, or comes down.

## Things worth fixing regardless

Found while building; reported in general terms. Details went to Planbook
directly.

- The edge configuration differs between hosts in a way that makes the WAF
  on one of them easy to sidestep.
- Creating an event with `noSchool=true` permanently deletes every lesson on
  that date, and deleting the event doesn't bring them back. This CLI warns
  first. The web app should too.

### Pre-launch: check how stored lesson text comes back

The postcondition compares lesson HTML byte for byte. If Planbook normalises
what it stores — wrapping a bare string in `<p>`, re-encoding an entity —
`lessons set --text` reports `PostconditionFailed` and exits 1 on a write that
landed. That error's remedy invites a retry, which
`decisions/2026-08-28-serial-requests.md` forbids.

`lessons set` is the core command, so one live round trip has to confirm this
before shipping: write text of each shape, read it back, and compare. If the
server normalises, the comparison has to normalise the same way.

## Two proposals

The server-side prerequisites are the same. The proposals differ in what sits
between the teacher and the API.

### Proposal A — CLI with proper auth

What this repo already is, with the authentication fixed.

- Authorization code + PKCE with a loopback listener; device code as fallback.
- Refresh handling: renew in the background, fail cleanly on revoked grants.
- New failure modes: insufficient scope, revoked grant, rate limited — each
  with an exit code and a message that says what to do.
- Delete `auth import`, `auth token`, and the browser-cookie dependency.
- Migration: one release where both work and the old paths warn, then a
  release where only OAuth does.
- Handover: repo transferred or forked under Planbook's account, release
  pipeline moved, support path documented.

### Proposal B — Remote MCP server

A hosted service that speaks the
[Model Context Protocol](https://modelcontextprotocol.io/). Teachers connect
it to their AI assistant — Claude, ChatGPT, Gemini, or any MCP-capable
agent — and talk to Planbook in plain English. No install, no terminal, no
Python.

**Why MCP fits here:**

- MCP is an open standard under the
  [Linux Foundation](https://www.linuxfoundation.org/press/linux-foundation-launches-open-standard-for-ai-agents),
  supported by Anthropic, OpenAI, Google, Microsoft, and AWS. Claude,
  [ChatGPT](https://openai.com/index/adding-mcp-support-to-chatgpt/), and
  [Gemini](https://developers.googleblog.com/en/gemini-api-and-google-ai-studio-now-support-mcp/)
  all call MCP servers natively. One server reaches every major agent platform.
- Tools are self-describing. An agent discovers what `lessons_set` does, what
  parameters it takes, and what scopes it needs — no documentation or `--help`
  flags.
- The [spec mandates OAuth 2.1 with PKCE](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization)
  for remote servers — the same auth posture Proposal A needs. A teacher
  authenticates once through a consent screen; the server handles token
  lifecycle from there.
- The [latest spec revision](https://blog.modelcontextprotocol.io/posts/2026-07-28/)
  made the protocol stateless: plain HTTP, works behind standard load
  balancers. Running an MCP server is about as complex as running a REST API.
- Planbook's EdTech peers already ship MCP servers.
  [Canvas](https://community.canvaslms.com/t5/canvas-releases/canvas-mcp-server/ta-p/627082),
  D2L Brightspace, and Khan Academy have them. A Planbook MCP server is not
  pioneering; it is table stakes for AI-assisted teaching tools.

**What the server exposes:**

Every CLI command maps to an MCP tool. The domain knowledge — endpoint mapping,
full-record-replace semantics, `Y`/`N` booleans, the `noSchool` data-loss
guard — becomes the server's implementation rather than instructions an agent
has to read from a config file.

Each tool declares its required scopes. An agent requesting `lessons_set` that
only holds `planbook.lessons.read` gets a clear error, not a silent failure.

**Hosting:**

Planbook runs the server, or delegates it to a managed edge platform. The
teacher's machine runs nothing.

**Distribution:**

The server URL goes into agent connector marketplaces — Claude's connectors
page, ChatGPT's integrations, Gemini's extensions. A teacher finds "Planbook"
in the list, clicks connect, authenticates, and starts talking. This is
distribution the CLI can never match.

**Security note:** The MCP ecosystem has had real security problems — a
[2026 audit by OX Security](https://www.ox.security/the-model-context-protocol-vulnerability-report/)
found ~200,000 vulnerable server instances, and
[GitGuardian found 24,000 leaked secrets](https://blog.gitguardian.com/model-context-protocol-mcp-security/)
in MCP config files on public GitHub. A remote server with proper OAuth
sidesteps the worst of these because the teacher never handles tokens or edits
config files. The attack surface is the server itself, which Planbook controls,
not thousands of local installs.

## Tradeoffs

| | CLI (Proposal A) | MCP server (Proposal B) |
|---|---|---|
| **Install** | `pip install planbook-cli`, needs Python | None — connect in the agent's UI |
| **Who can use it** | Teachers willing to install cli tools | Any teacher with an AI assistant |
| **Agent support** | Claude Code and terminal-based agents | Claude, ChatGPT, Gemini, and any MCP client |
| **Infrastructure** | Zero — runs on the teacher's machine | Planbook hosts a service |
| **Tool discovery** | Agent reads config or `--help` | Agent discovers tools from the protocol |
| **Auth surface** | Token on teacher's machine | Token managed server-side; teacher never sees it |
| **Blast radius** | One teacher's machine | Every connected teacher |
| **Updates** | Teacher runs `pip install --upgrade` | Planbook deploys; instant for everyone |
| **Distribution** | PyPI, GitHub | Agent connector marketplaces |

The MCP server is the stronger path for reaching teachers. Most teachers don't
have Python installed and don't want a terminal. The CLI is the stronger path
for power users and AI coding assistants that already operate in a terminal.

## Building both from shared logic

The two proposals are not mutually exclusive.

The CLI already contains the hard part: domain logic that maps teacher intent
to API calls, handles the API's quirks, and guards against destructive
operations. That logic can be extracted into a shared library that both the
CLI and the MCP server import.

```
planbook-core/          # shared library
  api/                  # HTTP client, auth, error handling
  domain/               # classes, lessons, units, events, etc.
  guards/               # destructive-operation checks

planbook-cli/           # thin CLI layer: argparse, exit codes, stdout/stderr
  uses planbook-core

planbook-mcp/           # thin MCP layer: tool definitions, protocol handling
  uses planbook-core
```

A bug fix or a new endpoint lands once in `planbook-core` and ships to both
surfaces. Proposal A is not throwaway work if Proposal B is the long-term
answer — the CLI is already the prototype of the core library.

## What Planbook could do with it

1. **Ship the MCP server.** Register the OAuth client, extract the shared
   library, build the MCP tool layer, host it, and list it in the connector
   marketplaces. The CLI lives on as a community tool for power users.
2. **Ship the CLI first, MCP later.** The OAuth work is the same either way.
   Fix the CLI's auth now, extract the shared library when the MCP server is
   ready.
3. **Contract the finish.** Scope and price agreed up front for whichever path
   (or both): the OAuth work, the shared library, the MCP server, developer
   docs, and a handover.
4. **Do nothing.** The tool keeps working as long as the private API does, and
   the auth pattern stays as it is — which is the part nobody should want.
