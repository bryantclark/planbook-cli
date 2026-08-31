"""The one seam every write goes through.

A write is five steps in a fixed order: read the current record, build a
complete payload, preview it for `--dry-run`, send it, then decide whether it
took. The ordering *is* the safety property - Planbook replaces whole records
and answers HTTP 200 whether or not it stored anything - so it lives here
rather than in each resource module.

`preview` and `commit` produce the same envelope shape, so a caller can diff a
dry run against the result of the real one.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from .client import PlanbookClient
from .contract import CONTRACT_VERSION
from .errors import Ambiguous, PostconditionFailed, UsageError
from .fields import same
from .types import FormBody, JsonRecord, JsonValue, Method, Result
from .widen import json_of


@dataclass(frozen=True)
class Request:
    """One HTTP call, exactly as it will be sent."""

    endpoint: str
    payload: FormBody
    method: Method = "POST"

    def as_dict(self) -> Result:
        return {
            "method": self.method,
            "endpoint": self.endpoint,
            "payload": dict(self.payload),
        }


@dataclass
class Mutation:
    """A write, described end to end so it can be previewed or committed."""

    resource: str
    operation: str
    requests: list[Request]
    #: What the record looked like before, when the write read it first.
    before: JsonRecord | None = None
    #: Records destroyed beyond the one named, e.g. a class's lessons.
    cascade: Result = field(default_factory=dict)
    #: Anything else the caller should know: files uploaded, ids attached.
    effects: Result = field(default_factory=dict)
    #: Public field name -> (read-back key, value written), for every field
    #: the caller named. `commit` builds the postcondition from it, so a
    #: resource cannot change a field and forget to verify it. The public name
    #: is what `updated_fields` reports, so that stays stable even where the
    #: endpoint answers with a different key per account.
    named: dict[str, tuple[str, str]] = field(default_factory=dict)
    #: Public names in `named` whose value is a boolean, so the read-back
    #: compares them as one rather than by string.
    flags: frozenset[str] = frozenset()
    #: Public field name -> a predicate over the read-back, for a field a flat
    #: comparison cannot check - a class's schedule is a nested list, not a
    #: value. Listing one here *is* checking it: `commit` runs every predicate.
    checks: dict[str, Callable[[JsonRecord], bool]] = field(default_factory=dict)

    @property
    def updated_fields(self) -> list[str]:
        return sorted([*self.named, *self.checks])

    @property
    def destructive(self) -> bool:
        return self.operation == "delete" or bool(self.cascade)

    def envelope(self) -> Result:
        body: Result = {
            "contract": CONTRACT_VERSION,
            "resource": self.resource,
            "operation": self.operation,
            "destructive": self.destructive,
            "requests": [r.as_dict() for r in self.requests],
        }
        # The primary request is repeated at the top level, so a single-request
        # caller need not index into `requests`.
        if self.requests:
            body["endpoint"] = self.requests[0].endpoint
            body["payload"] = dict(self.requests[0].payload)
        body["updated_fields"] = list(self.updated_fields)
        if self.cascade:
            body["cascade"] = self.cascade
        if self.effects:
            body["effects"] = self.effects
        if self.before is not None:
            body["before"] = dict(self.before)
        return body


def preview(mutation: Mutation) -> Result:
    """The `--dry-run` result: the exact requests, and nothing sent."""
    return {"dry_run": True, **mutation.envelope()}


def require_intent(mutation: Mutation, *, confirmed: bool) -> None:
    """One destructive-action policy, applied to every resource.

    A delete that also destroys records the caller did not name needs `--yes`.
    """
    if not mutation.cascade or confirmed:
        return
    # Integer entries are counts; everything else is context for the preview.
    # A zero count is dropped: "0 lessons" reads as if nothing were at stake.
    counts = [(k, v) for k, v in mutation.cascade.items() if isinstance(v, int) and v]
    if counts:
        what = ", ".join(f"{v} {k if v != 1 else k.rstrip('s')}" for k, v in counts)
    elif any(not isinstance(v, int) for v in mutation.cascade.values()):
        # Defensive: every mapped cascade is a count.
        what = "more than the record named (" + ", ".join(mutation.cascade) + ")"
    else:
        what = f"this {mutation.resource}"
    raise UsageError(
        f"This destroys {what}, permanently. There is no undo. Pass --yes to "
        "confirm, or --dry-run to see the whole blast radius first.",
        details={"cascade": mutation.cascade},
        remedy="Re-run with --dry-run to inspect, then --yes to commit.",
    )


def commit(
    client: PlanbookClient,
    mutation: Mutation,
    *,
    read: Callable[[], JsonRecord | None] | None = None,
    verify: Callable[[], object] | None = None,
    result: JsonRecord | None = None,
) -> Result:
    """Send the requests in order, then check the write actually took.

    `read` re-reads the record. For a create or an update the seam compares it
    against `mutation.named`, so existence alone is never enough; for a delete
    it must come back empty. `verify` is the escape hatch for a postcondition
    that is not a field comparison. Planbook reports success either way.
    """
    for request in mutation.requests:
        send(client, request)

    if read is not None:
        verify = (
            read if mutation.operation == "delete" else _stored_as_named(read, mutation)
        )

    if verify is not None:
        found = _read_back(verify, mutation)
        gone = mutation.operation == "delete"
        if bool(found) is gone:
            raise PostconditionFailed(
                f"{mutation.resource} {mutation.operation} reported success but "
                + ("the record is still there." if gone else "stored nothing."),
                details={
                    "resource": mutation.resource,
                    "operation": mutation.operation,
                    "endpoint": mutation.requests[-1].endpoint
                    if mutation.requests
                    else None,
                },
            )

    body: Result = {"ok": True, **dict(result or {})}
    body.setdefault("updated_fields", list(mutation.updated_fields))
    if mutation.cascade:
        body["cascade"] = mutation.cascade
    if mutation.effects:
        body["effects"] = mutation.effects
    return body


def _read_back(verify: Callable[[], object], mutation: Mutation) -> object:
    """Run the postcondition read, or say the write is unverifiable.

    The write has already landed. Letting the read's own error through would
    hand the caller a remedy that says retry.
    """
    try:
        return verify()
    except Exception as exc:
        raise Ambiguous(
            f"The {mutation.resource} {mutation.operation} was sent, but "
            f"reading it back failed: {exc}",
            details={
                "resource": mutation.resource,
                "operation": mutation.operation,
                "read_back_error": getattr(exc, "kind", type(exc).__name__),
            },
        ) from exc


def _stored_as_named(
    read: Callable[[], JsonRecord | None], mutation: Mutation
) -> Callable[[], object]:
    """The postcondition for a create or an update.

    Every field the caller named must come back as written - checking a field
    that was only carried over compares a value against itself, and passes
    whether or not the server stored anything. A create names nothing, so
    there existence is all that can be proven.
    """

    def check() -> object:
        record = read()
        if record is None:
            return None
        if not all(
            same(record.get(key), value, is_flag=public in mutation.flags)
            for public, (key, value) in mutation.named.items()
        ):
            return None
        if not all(predicate(record) for predicate in mutation.checks.values()):
            return None
        return record

    return check


def send(client: PlanbookClient, request: Request) -> JsonValue:
    if request.method == "GET":
        return client.get(request.endpoint, request.payload)
    if request.method == "POST-json":
        return client.post_json(request.endpoint, json_of(request.payload))
    return client.post(request.endpoint, request.payload)


def resolve_created(
    *,
    resource: str,
    before: set[str],
    after: Iterable[JsonRecord],
    id_of: Callable[[JsonRecord], object],
    matches: Callable[[JsonRecord], bool],
    list_command: str,
) -> object:
    """The id of the record this write created.

    Planbook's create endpoints do not report an id, so it is recovered by
    diffing the list around the write. If several records appeared - a second
    device, a shared account - the ones not matching what was written are
    discarded before giving up.
    """
    fresh = [r for r in after if str(id_of(r)) not in before]
    if len(fresh) == 1:
        return id_of(fresh[0])
    if not fresh:
        raise PostconditionFailed(
            f"Creating the {resource} did not take: no new {resource} appeared. "
            "The server returns HTTP 200 even when it stores nothing.",
            details={"resource": resource},
        )
    narrowed = [r for r in fresh if matches(r)]
    if len(narrowed) == 1:
        return id_of(narrowed[0])
    raise Ambiguous(
        f"{len(fresh)} {resource} records appeared while this one was created, "
        f"and {len(narrowed)} of them match what was written, so the new id "
        "cannot be proven.",
        details={
            "resource": resource,
            "candidates": [id_of(r) for r in (narrowed or fresh)],
            "list_command": list_command,
        },
        remedy=f"The {resource} exists - do not retry. Run `{list_command}`.",
    )
