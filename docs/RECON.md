# Mapping more endpoints

`planbook endpoints` lists what is understood today. Most of Planbook is not on that
list. This is how to add to it.

The API is undocumented, so the only source of truth is what the web app actually
sends. Everything below is observation, not guesswork.

## 1. Record traffic from a signed-in session

Sign in to `app.planbook.com` in a normal browser. Open DevTools, Network tab,
filter to Fetch/XHR. Then perform the single action you want to script - add one
assignment, mark one attendance, whatever it is.

You are looking for one request. Planbook's UI is chatty, but the write is almost
always a lone POST to `api.planbook.com` fired at the moment you hit save.

For read endpoints the calls happen at page load, before you can start recording.
Either reload with the Network tab already open, or list them from the console:

```js
[...new Set(performance.getEntriesByType('resource')
  .map(e => new URL(e.name))
  .filter(u => u.host.includes('planbook'))
  .map(u => u.pathname))].sort()
```

## 2. Read the payload, not just the path

Right-click the request, Copy as cURL. The body is form-encoded, and the field
*values* matter as much as the names, because Planbook's conventions are not
guessable:

- integers are `0` when absent, never `""` (an empty string returns a Java NPE)
- booleans are `Y`/`N`, except a few that are literal `true`/`false`
- dates are `MM/DD/YYYY`

When adding an endpoint, capture a real request and copy its conventions exactly
rather than inferring them from the field name.

## 3. Try it through `raw` first

```bash
planbook raw /getAssignments -F classId=12345678 --dry-run   # inspect
planbook raw /getAssignments -F classId=12345678             # send
```

`raw` applies no conventions for you, which makes it the right place to find out
what the endpoint actually wants. If it returns `{"error":"true","msg":...}`, the
message usually names the field it choked on.

## 4. Promote it

Once the call works reliably:

1. add a function to `src/planbook/api.py`, translating abbreviated wire keys to
   readable ones on the way out
2. add a subcommand in `src/planbook/cli.py`
3. move the entry in `src/planbook/endpoints.py` from `observed` to `mapped`
   (or `partial`, if the request works but the response is not decoded)
4. document it in `AGENTS.md` - the agent contract, not an afterthought
5. add a test with a recorded response fixture; no test should hit the network

## Rules of the road

- **Use your own account.** Never another user's data.
- **Serialize requests.** No parallelism, no retry loops. Planbook explicitly
  reserves the right to rate-limit.
- **Identify honestly.** The User-Agent says what this is. Do not spoof a browser -
  their ToS forbids forging identifiers to disguise origin, and there is no reason
  to need it.
- **Never make API calls against `app.planbook.com`.** It sits behind an AWS WAF,
  and defeating bot detection is out of scope for this project, permanently. The
  API host has no such protection and is the supported path. (`auth browser` opens
  a headed window there for a human to sign in, which passes the WAF the ordinary
  way; nothing automated is attempted against that host.)
- **Prefer failing loudly.** If a response does not look right, raise `SchemaDrift`
  rather than parsing optimistically. A crash is recoverable; a planbook quietly
  filled with wrong lessons is not.
