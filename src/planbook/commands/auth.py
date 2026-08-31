"""Authentication command callbacks."""

from __future__ import annotations

import argparse
import contextlib
import getpass
import os
import sys
import time
import webbrowser
from typing import NoReturn

from .. import browser_cookies, config
from .. import token as pbtoken
from ..cli_support import emit
from ..client import PlanbookClient
from ..errors import (
    SIGN_IN_HELP,
    SIGN_IN_URL,
    ApiError,
    NotAuthenticated,
    PlanbookError,
    UsageError,
)
from ..narrow import text
from ..resources.classes import list_classes


def cmd_auth_token(args: argparse.Namespace) -> None:
    """Store a Planbook access token copied out of a signed-in browser.

    Accepts a bare JWT, a Cookie header, or a "Copy as cURL" paste. Verified
    before it is stored.
    """
    raw = args.value or getpass.getpass("Paste token, cookie, or curl: ")
    value = pbtoken.extract(raw)
    if not value:
        raise UsageError(
            "No access token found in that input.\n"
            "Paste the JWT itself, or a request copied with DevTools -> "
            "Network -> right-click a call to api.planbook.com -> Copy as cURL. "
            "The token is the cookie named U|...|.accesstoken - NOT the SESSION "
            "cookie, which is not what authenticates you."
        )

    info = pbtoken.describe(value)
    if pbtoken.is_expired(value):
        raise UsageError(
            "That token has already expired. Reload Planbook in your browser "
            "and copy a fresh one."
        )

    if not args.no_verify:
        client = PlanbookClient(value, verbose=args.verbose)
        list_classes(client)  # raises NotAuthenticated if the token is bad

    path = config.save_session(value, text(info, "email"))
    emit(
        {
            "ok": True,
            "stored": str(path),
            "verified": not args.no_verify,
            "email": info.get("email"),
            "expires_in_hours": info.get("expires_in_hours"),
        }
    )


def _best_browser_token(args: argparse.Namespace) -> tuple[int, str, str] | None:
    """The longest-lived usable token across local browsers, or None.

    Auth-server tokens last about an hour, so a browser signed in earlier can
    hold a nearly-dead token while another holds a fresh one; take the freshest.
    """
    best: tuple[int, str, str] | None = None
    preferred = args.browser
    if not preferred:
        from ..default_browser import default_browser_name

        name = default_browser_name()
        if name:
            preferred = name.split()[0].lower()
    for browser, candidate in browser_cookies.search(preferred):
        if pbtoken.is_expired(candidate):
            continue
        remaining = _seconds_left(candidate)
        if best is not None and remaining <= best[0]:
            continue
        try:
            list_classes(PlanbookClient(candidate, verbose=args.verbose))
        except PlanbookError:
            # A rejected token does not reliably say notLoggedIn - one
            # answered "date must not be null" - so any failure disqualifies.
            continue
        best = (remaining, browser, candidate)
    return best


def _store_token(browser: str, token: str) -> None:
    info = pbtoken.describe(token)
    path = config.save_session(token, text(info, "email"))
    emit(
        {
            "ok": True,
            "stored": str(path),
            "source": browser,
            "email": info.get("email"),
            "expires_in_hours": info.get("expires_in_hours"),
        }
    )


def cmd_auth_import(args: argparse.Namespace) -> None:
    """Read the access token from a browser you are already signed in to.

    In a terminal with no token found, opens the sign-in page and waits for
    you, then takes the token.
    """
    print(
        "Reading browser cookies. macOS may raise a Keychain prompt - approve "
        "it to continue (choose Always Allow to skip it next time).",
        file=sys.stderr,
    )
    best = _best_browser_token(args)

    # Never trade down: an already-stored session may outlive every cookie.
    stored = config.load_session_or_none()
    if stored and not pbtoken.is_expired(stored):
        held = _seconds_left(stored)
        if best is None or held >= best[0]:
            info = pbtoken.describe(stored)
            emit(
                {
                    "ok": True,
                    "stored": str(config.session_path()),
                    "source": "kept the stored token; no browser had a fresher one",
                    "email": info.get("email"),
                    "expires_in_hours": info.get("expires_in_hours"),
                }
            )
            return

    if best is not None:
        _remaining, browser, candidate = best
        _store_token(browser, candidate)
        return

    # Nothing found. In a terminal, guide the sign-in and poll for a token.
    # Without a TTY, raise instead: an agent or CI run must never hang.
    interactive = sys.stdin.isatty() and sys.stderr.isatty() and not args.no_wait
    if interactive:
        _guided_sign_in(args)
        return

    _no_token_error()


def _guided_sign_in(args: argparse.Namespace) -> None:
    # Polling a cookie store this tool cannot read never ends. Safari on macOS
    # is the common case, blocked without Full Disk Access.
    if not browser_cookies.any_store_readable():
        raise UsageError(
            "This tool reads the sign-in token from your browser's cookie "
            "store, and none it can read is available here.\n"
            "Safari's store is blocked on macOS without Full Disk Access, so "
            "the easy paths are:\n"
            "  - sign in with Chrome, Brave, Edge, Vivaldi, Opera or Firefox, "
            "then rerun `planbook auth import`, or\n"
            "  - paste a token once with `planbook auth token` (works from any "
            "browser)."
        )
    print(
        f"\nNot signed in yet. Opening {SIGN_IN_URL} in your browser.\n"
        "Sign in there (normal window, your usual Google login), then come "
        "back here - this will pick up automatically.\n"
        "Use Chrome, Brave, Edge, Vivaldi, Opera or Firefox - Safari's cookies "
        "cannot be read without Full Disk Access.",
        file=sys.stderr,
    )
    with contextlib.suppress(Exception):
        webbrowser.open(SIGN_IN_URL)

    deadline = time.monotonic() + args.wait_timeout
    while time.monotonic() < deadline:
        time.sleep(3)
        best = _best_browser_token(args)
        if best is not None:
            _remaining, browser, candidate = best
            print("Got it.", file=sys.stderr)
            _store_token(browser, candidate)
            return
        left = int(deadline - time.monotonic())
        print(f"  waiting for sign-in... {left}s left", file=sys.stderr)

    _no_token_error()


def _no_token_error() -> NoReturn:
    report = browser_cookies.diagnose()
    lines = "\n".join(f"  {b:8} {status}" for b, status in report.items())
    raise UsageError(
        "No usable Planbook token found in any local browser.\n" + lines + "\n\n"
        f"Sign in at {SIGN_IN_URL} first, then run `planbook auth import` again.\n"
        "If a browser above says 'locked', macOS denied Keychain access - rerun "
        "and choose Always Allow.\n"
        "If you would rather not grant that, use `planbook auth token` instead."
    )


def cmd_auth_status(args: argparse.Namespace) -> None:
    raw = config.load_session()
    info = pbtoken.describe(raw)
    client = PlanbookClient(raw, verbose=args.verbose)
    status = {
        "authenticated": True,
        "source": "env" if config.TOKEN_ENV in os.environ else "file",
        "email": info.get("email"),
        "account_id": info.get("account_id"),
        "expires_in_hours": info.get("expires_in_hours"),
    }
    try:
        body = list_classes(client)
    except ApiError as exc:
        # A token the server has stopped honouring does not reliably come back
        # as notLoggedIn - one answered "date must not be null". Drift and
        # transport failures keep their own codes; neither means "sign in".
        raise NotAuthenticated(
            f"The stored token was rejected: {exc}" + SIGN_IN_HELP
        ) from exc
    emit(
        {
            **status,
            "current_year_id": body["current_year_id"],
            "class_count": len(body["classes"]),
        }
    )


def cmd_auth_logout(_args: argparse.Namespace) -> None:
    emit({"cleared": config.clear_session()})


def _seconds_left(token: str) -> int:
    """How long a token has to live, in whole seconds."""
    value = pbtoken.describe(token).get("expires_in_seconds")
    return int(value) if isinstance(value, int | float) else 0
