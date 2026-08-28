"""Login against auth.planbook.com.

The login page is a plain Spring Security form: POST username + password +
a `_csrf` token scraped from the page you just fetched. There is no OAuth
dance and no JSON endpoint, so the flow is:

    GET  /login          -> collect the CSRF token and a pre-auth SESSION
    POST /login          -> exchange credentials for an authenticated SESSION
    POST /getClasses2    -> confirm the session actually works

The last step matters: Planbook answers a bad login with HTTP 200 and an
HTML page, so nothing short of a real API call proves success.
"""

from __future__ import annotations

import re
from typing import Iterator

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
    """Yield every distinct SESSION value in the jar, newest-looking first."""
    seen: list[str] = []
    for cookie in http.cookies:
        if cookie.name == "SESSION" and cookie.value and cookie.value not in seen:
            seen.append(cookie.value)
    # Reverse: the post-login cookie is set after the pre-auth one.
    yield from reversed(seen)


def _works(cookie: str) -> bool:
    probe = requests.Session()
    probe.headers["User-Agent"] = USER_AGENT
    probe.cookies.set("SESSION", cookie, domain=".planbook.com")
    try:
        resp = probe.post(f"{API_BASE}/getClasses2", timeout=30)
        body = resp.json()
    except Exception:
        return False
    return isinstance(body, dict) and str(body.get("notLoggedIn", "")).lower() != "true"


def login(username: str, password: str) -> str:
    """Return an authenticated SESSION cookie value.

    Raises :class:`LoginFailed` with a specific reason rather than a generic
    failure, so an agent can tell a wrong password from a changed login form.
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
        "Login did not produce a working session. The usual cause is a wrong "
        "email or password. If those are correct, the account may use SSO "
        "(Google/Microsoft/Clever/ClassLink/Apple), which this CLI cannot drive - "
        "sign in through a browser and use `planbook auth cookie <SESSION>` instead."
    )
