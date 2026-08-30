"""Read the access token out of a browser you are already signed in to.

The recommended path: no browser is driven and nothing is impersonated, so
identity providers never see automation. It only reads a cookie store the
user already owns.

On macOS that store is behind the Keychain; the first-run prompt is the
consent boundary, and "Always Allow" makes later runs silent.
"""

from __future__ import annotations

import contextlib
import signal
from collections.abc import Iterator
from typing import Any

from .errors import LoginFailed

# Order matters: the default browser is tried first by the caller, then these.
KNOWN_BROWSERS = ("brave", "chrome", "edge", "vivaldi", "opera", "firefox", "safari")

TOKEN_SUFFIX = ".accesstoken"


def _import_bc() -> Any:
    try:
        import browser_cookie3
    except ImportError as exc:
        raise LoginFailed(
            "Reading browser cookies needs browser-cookie3:\n"
            "  pip install 'planbook-cli[local]'"
        ) from exc
    return browser_cookie3


class CookieTimeout(Exception):
    """Reading a browser's cookie store took too long."""


@contextlib.contextmanager
def _time_limit(seconds: int) -> Iterator[None]:
    """Bound a blocking read.

    macOS gates the cookie store behind the Keychain, and an unanswered
    prompt blocks forever. Without this the command simply hangs with no
    output and no explanation.
    """
    if not hasattr(signal, "SIGALRM"):  # pragma: no cover - non-POSIX
        yield
        return

    def _raise(_signum: int, _frame: object) -> None:
        raise CookieTimeout

    previous = signal.signal(signal.SIGALRM, _raise)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def tokens_from(browser: str, *, timeout: int = 10) -> list[str]:
    """Return any Planbook access tokens found in one browser's cookie store."""
    bc = _import_bc()
    loader = getattr(bc, browser, None)
    if loader is None:
        raise LoginFailed(f"Unknown browser {browser!r}.")
    with _time_limit(timeout):
        jar = loader(domain_name="planbook.com")
        return [c.value for c in jar if c.name.endswith(TOKEN_SUFFIX) and c.value]


def search(preferred: str | None = None) -> Iterator[tuple[str, str]]:
    """Yield (browser, token) for every Planbook token found locally.

    Missing or locked browsers are skipped, not raised: one locked store
    should not stop the search.
    """
    order = list(KNOWN_BROWSERS)
    if preferred:
        order = [preferred] + [b for b in order if b != preferred]
    for browser in order:
        try:
            for token in tokens_from(browser):
                yield browser, token
        except Exception:
            continue


def any_store_readable() -> bool:
    """True if at least one browser's cookie store can be read at all.

    A store that answers - even with no Planbook token - is readable. Safari on
    macOS is not, without Full Disk Access, so a Safari-only machine returns
    False and the caller can say so instead of polling a store it can never read.
    """
    bad = ("unreadable", "locked", "not installed", "timed out")
    for status in diagnose().values():
        if not any(flag in status for flag in bad):
            return True
    return False


def diagnose() -> dict[str, str]:
    """Per-browser status, for when the search finds nothing useful."""
    report: dict[str, str] = {}
    for browser in KNOWN_BROWSERS:
        try:
            found = tokens_from(browser)
            report[browser] = f"{len(found)} token(s)" if found else "no Planbook token"
        except Exception as exc:
            message = str(exc)
            if isinstance(exc, CookieTimeout):
                report[browser] = "timed out (unanswered Keychain prompt?)"
            elif "key for cookie decryption" in message.lower():
                report[browser] = "locked (Keychain access denied)"
            elif (
                "not installed" in message.lower()
                or "could not find" in message.lower()
            ):
                report[browser] = "not installed"
            else:
                report[browser] = f"unreadable: {message[:60]}"
    return report
