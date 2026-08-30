# Mapping more endpoints

`planbook endpoints` lists what is understood today. Most of Planbook is not on that
list. This is how to add to it.

The API is undocumented, so the only source of truth is what the web app sends.

## 1. Record traffic from a signed-in session

Sign in to `app.planbook.com` in a normal browser. Open DevTools > Network, filter to
Fetch/XHR, then perform the single action you want to script.

You are looking for one request. The UI is chatty, but the write is almost always a
lone POST to `api.planbook.com` fired when you hit save.

Read endpoints fire at page load, before you can start recording. Reload with the
Network tab open, or list them from the console:

```js
[...new Set(performance.getEntriesByType('resource')
  .map(e => new URL(e.name))
  .filter(u => u.host.includes('planbook'))
  .map(u => u.pathname))].sort()
```

## 2. Read the payload, not only the path

Copy the request as cURL. The body is form-encoded, and the field *values* matter as
much as the names. See [API-NOTES](API-NOTES.md) for the conventions. Copy a real
request exactly rather than inferring from the field name.

## 3. Try it through `raw` first

```bash
planbook raw /services/planbook/student/studentsTagged --get --dry-run   # inspect
planbook raw /services/planbook/student/studentsTagged --get             # send
```

`raw` applies no conventions for you, which makes it the right place to find out what
the endpoint wants. Probe with a read first. On an `/update*` path a partial payload
replaces the whole record. On `{"error":"true","msg":...}`, the message usually names the
field it choked on.

## 4. Promote it

1. Add the function to the matching `src/planbook/resources/*.py`, translating wire
   keys to readable ones, then re-export it from `src/planbook/api.py`.
2. Wire the parser in `src/planbook/cli.py::build_parser`, and put the callback in
   `src/planbook/commands/<area>.py`.
3. Move the entry in `src/planbook/endpoints.py` from `observed` to `mapped`, or to
   `partial` if the request works but the response isn't decoded.
4. Document it in `AGENTS.md`, and record its wire conventions and gotchas in
   [API-NOTES](API-NOTES.md). If the command is destructive, add it to
   `skills/planbook/SKILL.md` too.
5. Add a test with a recorded response fixture. No test hits the network.

Use your own account, never another user's data.
