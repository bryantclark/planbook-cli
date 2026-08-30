# Mapping more endpoints

`planbook endpoints` lists what's mapped today. This is how to add to it.

## 1. Record traffic

Sign in to `app.planbook.com`. Open DevTools > Network > Fetch/XHR. Perform the
action you want to script. Look for a single POST to `api.planbook.com` at save
time.

For read endpoints (fired at page load), reload with the Network tab open or run:

```js
[...new Set(performance.getEntriesByType('resource')
  .map(e => new URL(e.name))
  .filter(u => u.host.includes('planbook'))
  .map(u => u.pathname))].sort()
```

## 2. Read the payload

Right-click > Copy as cURL. Copy conventions exactly from a real request —
see [API-NOTES.md, Conventions](API-NOTES.md#conventions).

## 3. Test through `raw`

```bash
planbook raw /getAssignments -F classId=12345678 --dry-run
planbook raw /getAssignments -F classId=12345678
```

## 4. Promote it

1. Add a function to `src/planbook/api.py` (translate wire keys to readable ones)
2. Add a subcommand in `src/planbook/cli.py`
3. Move the entry in `src/planbook/endpoints.py` from `observed` to `mapped`
4. Document it in `AGENTS.md`
5. Add a test with a recorded response fixture (no network calls)

## Rules

- **Use your own account.** Never another user's data.
- All other rules (serialize requests, honest User-Agent, fail loudly, never hit `app.planbook.com`) are in `AGENTS.md` and `decisions/`.
