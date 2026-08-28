"""Read the access token out of a browser you are already signed in to.

The recommended path: no browser is driven and nothing is impersonated, so
identity providers never see automation. It only reads a cookie store the
user already owns.

On macOS that store is behind the Keychain; the first-run prompt is the
consent boundary, and "Always Allow" makes later runs silent.
"""

from __future__ import annotations

from typing import Iterator

from .errors import LoginFailed

# Order matters: the default browser is tried first by the caller, then these.
KNOWN_BROWSERS = ("brave", "chrome", "edge", "vivaldi", "opera", "firefox", "safari")

TOKEN_SUFFIX = ".accesstoken"


def _import_bc():
    try:
        import browser_cookie3
    except ImportError as exc:
        raise LoginFailed(
            "Reading browser cookies needs browser-cookie3:\n"
            "  pip install 'planbook-cli[local]'"
        ) from exc
    return browser_cookie3


def tokens_from(browser: str) -> list[str]:
    """Return any Planbook access tokens found in one browser's cookie store."""
    bc = _import_bc()
    loader = getattr(bc, browser, None)
    if loader is None:
        raise LoginFailed(f"Unknown browser {browser!r}.")
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


def diagnose() -> dict[str, str]:
    """Per-browser status, for when the search finds nothing useful."""
    report: dict[str, str] = {}
    for browser in KNOWN_BROWSERS:
        try:
            found = tokens_from(browser)
            report[browser] = f"{len(found)} token(s)" if found else "no Planbook token"
        except Exception as exc:
            message = str(exc)
            if "key for cookie decryption" in message.lower():
                report[browser] = "locked (Keychain access denied)"
            elif "not installed" in message.lower() or "could not find" in message.lower():
                report[browser] = "not installed"
            else:
                report[browser] = f"unreadable: {message[:60]}"
    return report
