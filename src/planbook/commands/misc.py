"""Miscellaneous command callbacks."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.parse import urlsplit

from ..cli_support import client_from, emit, teacher_id_from, year_id_from
from ..client import PlanbookClient
from ..errors import PlanbookError, UsageError
from ..mutations import Mutation, Request, preview, require_intent
from ..resources.misc import (
    list_attachments,
    raw_standards,
    settings,
    simple_read,
    special_days,
    standards,
    upload,
)
from ..types import FormPayload, Method, Result
from ..widen import json_of


def cmd_schedule_special_days(args: argparse.Namespace) -> None:
    emit(
        special_days(
            client_from(args),
            teacher_id=teacher_id_from(args),
            year_id=year_id_from(args),
            school_id=args.school_id,
        )
    )


def cmd_settings(args: argparse.Namespace) -> None:
    emit(settings(client_from(args)))


def cmd_standards(args: argparse.Namespace) -> None:
    client = client_from(args)
    emit(
        raw_standards(client)
        if args.raw
        else standards(client, search=args.search or "")
    )


def cmd_simple_read(args: argparse.Namespace) -> None:
    emit(simple_read(client_from(args), args.command, raw=args.raw))


def cmd_attachments_list(args: argparse.Namespace) -> None:
    emit(list_attachments(client_from(args), teacher_id=teacher_id_from(args)))


def cmd_attachments_upload(args: argparse.Namespace) -> None:
    # Every path is checked before any file is sent: a bad name halfway
    # through would otherwise leave earlier uploads done and unreported,
    # because stdout stays empty on failure.
    missing = [f for f in args.files if not Path(f).is_file()]
    if missing:
        raise UsageError(f"No such file: {', '.join(missing)}. Nothing was sent.")
    # A dry run reads the clash list too: an absent `effects` must mean the
    # upload replaces nothing, not that nobody looked.
    client = client_from(args)
    clashes = _replaced_names(client, args, args.files, dry_run=args.dry_run)
    results = [
        upload(
            client,
            f,
            dry_run=args.dry_run,
            # None means the lookup failed, which is not the same answer
            # as "replaces nothing".
            replaces=None if clashes is None else Path(f).name in clashes,
        )
        for f in args.files
    ]
    if not args.dry_run:
        _report_stored(client, args, results)
    emit(results)


def _report_stored(
    client: PlanbookClient, args: argparse.Namespace, results: list[Result]
) -> None:
    """Read the resource list back and say whether each upload is in it.

    `/uploadAttachment` answers with a URL rather than a receipt, so the list
    is the only evidence a file reached the account. One read covers the whole
    batch.

    This reports; it does not fail. Every other write raises
    `PostconditionFailed` when the read-back disagrees, but the list keys files
    by `fileKey` and nothing proves that is the file's own name on every
    account. A wrong guess there would call a good upload a failure, so the
    answer goes in `verified` for the caller to judge: true, false, or null
    when the lookup itself failed.
    """
    try:
        held = list_attachments(client, teacher_id=teacher_id_from(args))
    except PlanbookError:
        for result in results:
            result["verified"] = None
        return
    names = {str(a["name"]) for a in held}
    paths = {urlsplit(str(a["url"])).path for a in held}
    for result in results:
        found = str(result.get("name")) in names or (
            urlsplit(str(result.get("url"))).path in paths
        )
        result["verified"] = found
        if not found:
            print(
                f"warning: {result.get('name')} uploaded but is not in the "
                "account's resource list; check `planbook attachments list`",
                file=sys.stderr,
            )


def _replaced_names(
    client: PlanbookClient,
    args: argparse.Namespace,
    files: list[str],
    *,
    dry_run: bool,
) -> set[str] | None:
    """The upload names the account already holds, warned about on stderr.

    A same-named upload replaces the stored file in every lesson linked to it,
    and the server reports that as an ordinary success.

    A dry run has sent nothing yet, so a failure here is fatal: reporting "no
    clash" when nobody could look is the one answer a preview must not give.
    On the real run any `PlanbookError` - the API's own errors, but also a
    timeout, a 5xx or a changed response shape - is reported as an unknown
    rather than swallowed into a clean result. Anything lower still aborts
    before a file is sent.
    """
    try:
        held = {
            str(a["name"])
            for a in list_attachments(client, teacher_id=teacher_id_from(args))
        }
    except PlanbookError:
        if dry_run:
            raise
        return None
    clashes = {Path(f).name for f in files} & held
    if clashes:
        print(
            f"warning: replaces the existing resource(s) {', '.join(sorted(clashes))} "
            "in every lesson linked to them",
            file=sys.stderr,
        )
    return clashes


def cmd_raw(args: argparse.Namespace) -> None:
    """POST to any endpoint. The escape hatch for unmapped calls."""
    # A repeated key becomes a list, not an overwrite: standardDBIds and
    # friends need repeated fields, and a comma-joined value clears the set.
    payload: FormPayload = {}
    for pair in args.field:
        if "=" not in pair:
            raise UsageError(f"--field expects key=value, got {pair!r}")
        key, value = pair.split("=", 1)
        if key in payload:
            seen = payload[key]
            payload[key] = [*seen, value] if isinstance(seen, list) else [seen, value]
        else:
            payload[key] = value
    method: Method = "GET" if args.get else ("POST-json" if args.json else "POST")
    # A POST here can reach /deleteClass as easily as /getAssignments, so it
    # counts as destructive until the caller says otherwise.
    mutation = Mutation(
        resource="raw",
        operation="request",
        requests=[Request(args.path, dict(payload), method=method)],
        assume_destructive=method != "GET",
    )
    if args.dry_run:
        emit(preview(mutation))
        return
    require_intent(mutation, confirmed=args.yes)
    client = client_from(args)
    if args.get:
        emit(client.get(args.path, payload))
    elif args.json:
        emit(client.post_json(args.path, json_of(payload)))
    else:
        emit(client.post(args.path, payload))
