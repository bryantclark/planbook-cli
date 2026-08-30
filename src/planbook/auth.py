"""Login against auth.planbook.com.

A plain Spring Security form - no OAuth, no JSON endpoint:

    GET  /login          -> scrape the CSRF token
    POST /login          -> exchange credentials for cookies
    POST /getClasses2    -> confirm the resulting token works

The last step matters: a bad login answers HTTP 200 with an HTML page, so
nothing short of a real API call proves success.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

import requests

from .client import API_BASE, AUTH_BASE, USER_AGENT
from .errors import LoginFailed

_CSRF_RE = re.compile(
    r'<input[^>]*name=["\']_csrf["\'][^>]*value=["\']([^"\']+)["\']', re.I
)


def _csrf_token(html: str) -> str:
    match = _CSRF_RE.search(html)
    if not match:
        raise LoginFailed(
            "Could not find a _csrf token on the login page. "
            "Planbook may have changed its login form."
        )
    return match.group(1)


def _session_cookies(http: requests.Session) -> Iterator[str]:
    """Yield every distinct access token in the jar, newest-looking first."""
    seen: list[str] = []
    for cookie in http.cookies:
        if (
            cookie.name.endswith(".accesstoken")
            and cookie.value
            and cookie.value not in seen
        ):
            seen.append(cookie.value)
    # Reverse: the post-login cookie is set after the pre-auth one.
    yield from reversed(seen)


def _works(token: str) -> bool:
    """True if this access token authenticates against the API.

    Only the Bearer JWT counts. `SESSION` is a decoy: the API issues one to
    anonymous callers too, so a hand-copied SESSION looks right and is not.
    """
    probe = requests.Session()
    probe.headers["User-Agent"] = USER_AGENT
    probe.headers["Authorization"] = f"Bearer {token}"
    try:
        resp = probe.post(f"{API_BASE}/getClasses2", timeout=30)
        body = resp.json()
    except Exception:
        return False
    # A usable token gets the real getClasses2 shape. Checking only notLoggedIn
    # is not enough: a rejected token can answer {"error":"true","msg":...} with
    # no notLoggedIn key, which would pass and get stored as if it worked.
    return (
        isinstance(body, dict)
        and str(body.get("notLoggedIn", "")).lower() != "true"
        and "classes" in body
        and "currentYearId" in body
    )


def login(username: str, password: str) -> str:
    """Return a working access token.

    Failures name their cause, so a wrong password is distinguishable from a
    changed login form.
    """
    http = requests.Session()
    http.headers["User-Agent"] = USER_AGENT

    try:
        page = http.get(f"{AUTH_BASE}/login", timeout=30)
    except requests.RequestException as exc:
        raise LoginFailed(f"Could not reach {AUTH_BASE}: {exc}") from exc

    token = _csrf_token(page.text)

    try:
        http.post(
            f"{AUTH_BASE}/login",
            data={"username": username, "password": password, "_csrf": token},
            timeout=30,
            allow_redirects=True,
        )
    except requests.RequestException as exc:
        raise LoginFailed(f"Login request failed: {exc}") from exc

    for cookie in _session_cookies(http):
        if _works(cookie):
            return cookie

    raise LoginFailed(
        "Login did not produce a working token. The usual cause is a wrong "
        "email or password. If those are correct, the account signs in with "
        "SSO, which this form login cannot drive - sign in to Planbook in your "
        "browser and run `planbook auth import` instead."
    )
