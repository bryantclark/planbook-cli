# Decisions

## API interaction

- [Read before every write](decisions/2026-08-28-read-before-write.md) — the server does full-record replace; omitted fields are blanked
- [Bearer header over cookie](decisions/2026-08-28-bearer-over-cookie.md) — `Authorization: Bearer <jwt>` works without cookies
- [Serial requests only](decisions/2026-08-28-serial-requests.md) — no parallelism, no retry loops; Planbook reserves rate limits
- [Fail on schema drift](decisions/2026-08-28-fail-on-schema-drift.md) — crash rather than guess when the API changes shape
- [One mutation seam](decisions/2026-08-30-one-mutation-seam.md) — every write is a `Mutation`; previews, ordering and postconditions live in one place

## Agent contract

- [Version the machine contract](decisions/2026-08-30-versioned-machine-contract.md) — `planbook schema`, structured errors, and a contract version agents can branch on

## Auth

- [Import from browser as default auth](decisions/2026-08-28-browser-import-auth.md) — sidesteps Google's automation-browser rejection
- [One auth path](decisions/2026-08-30-one-auth-path.md) — token import is the only sign-in, with paste as the manual fallback
