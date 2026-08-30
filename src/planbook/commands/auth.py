"""Authentication command callbacks."""

from __future__ import annotations

import argparse
import getpass
import os
import sys

from .. import api, auth, browser_auth, browser_cookies, config
from .. import token as pbtoken
from ..cli_support import emit
from ..client import PlanbookClient
from ..errors import NotAuthenticated, UsageError


def cmd_auth_login(args: argparse.Namespace) -> None:
    username = args.username or input("Email or user ID: ").strip()
    # Read from the TTY: never logged, never in argv, never stored.
    password = getpass.getpass("Password: ")
    cookie = auth.login(username, password)
    path = config.save_session(cookie, username)
    emit({"ok": True, "stored": str(path), "username": username})


def cmd_auth_token(args: argparse.Namespace) -> None:
    """Store a Planbook access token copied out of a signed-in browser.

    Accepts a bare JWT, a Cookie header, or a "Copy as cURL" paste. Verifies
    first, so a bad token fails here rather than three commands later.
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
        api.list_classes(client)  # raises NotAuthenticated if the token is bad

    path = config.save_session(value, info.get("email"))
    emit(
        {
            "ok": True,
            "stored": str(path),
            "verified": not args.no_verify,
            "email": info.get("email"),
            "expires_in_hours": info.get("expires_in_hours"),
        }
    )


def cmd_auth_import(args: argparse.Namespace) -> None:
    """Read the access token from a browser the user is already signed in to.

    The recommended path: nothing is automated and nothing is copied by hand.
    """
    from ..default_browser import default_browser_name

    preferred = args.browser
    if not preferred:
        name = default_browser_name()
        if name:
            preferred = name.split()[0].lower()

    print(
        "Reading browser cookies. macOS may raise a Keychain prompt - approve "
        "it to continue (choose Always Allow to skip it next time).",
        file=sys.stderr,
    )
    for browser, candidate in browser_cookies.search(preferred):
        if pbtoken.is_expired(candidate):
            continue
        client = PlanbookClient(candidate, verbose=args.verbose)
        try:
            api.list_classes(client)
        except NotAuthenticated:
            continue  # stale token from an old sign-in; try the next browser
        info = pbtoken.describe(candidate)
        path = config.save_session(candidate, info.get("email"))
        emit(
            {
                "ok": True,
                "stored": str(path),
                "source": browser,
                "email": info.get("email"),
                "expires_in_hours": info.get("expires_in_hours"),
            }
        )
        return

    report = browser_cookies.diagnose()
    lines = "\n".join(f"  {b:8} {status}" for b, status in report.items())
    from ..errors import SIGN_IN_URL

    raise UsageError(
        "No usable Planbook token found in any local browser.\n" + lines + "\n\n"
        f"Sign in at {SIGN_IN_URL} first, then run `planbook auth import` again.\n"
        "If a browser above says 'locked', macOS denied Keychain access - rerun "
        "and choose Always Allow.\n"
        "If you would rather not grant that, use `planbook auth token` instead."
    )


def cmd_auth_browser(args: argparse.Namespace) -> None:
    """Sign in by opening a browser and waiting for the user to do it.

    Discouraged (see README), but kept: it needs no manual copying, and would
    become the good path if Planbook ever registered an OAuth client.
    """
    if args.interactive:
        value = browser_auth.login_via_browser(
            timeout=args.timeout, channel=args.channel, profile=args.profile
        )
        interactive = True
    else:
        value, interactive = browser_auth.refresh_or_login(
            timeout=args.timeout, channel=args.channel, profile=args.profile
        )
    info = pbtoken.describe(value)
    path = config.save_session(value, info.get("email"))
    emit(
        {
            "ok": True,
            "stored": str(path),
            "method": "browser",
            "interactive": interactive,
            "email": info.get("email"),
            "expires_in_hours": info.get("expires_in_hours"),
        }
    )


def cmd_auth_status(args: argparse.Namespace) -> None:
    raw = config.load_session()
    info = pbtoken.describe(raw)
    client = PlanbookClient(raw, verbose=args.verbose)
    body = api.list_classes(client)
    emit(
        {
            "authenticated": True,
            "source": "env" if config.TOKEN_ENV in os.environ else "file",
            "email": info.get("email"),
            "account_id": info.get("account_id"),
            "expires_in_hours": info.get("expires_in_hours"),
            "current_year_id": body["current_year_id"],
            "class_count": len(body["classes"]),
        }
    )


def cmd_auth_logout(_args: argparse.Namespace) -> None:
    emit({"cleared": config.clear_session()})
