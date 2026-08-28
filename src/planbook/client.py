"""HTTP client for the Planbook private API.

Three things about this API drive the whole design:

1.  Failure arrives as HTTP 200 with an error body. Status codes tell you
    almost nothing, so every response goes through :meth:`_check`.
2.  Everything is form-encoded POST. There are no JSON request bodies and no
    verbs other than POST.
3.  Empty string is not the same as absent. Integer-typed fields must be "0";
    sending "" triggers a server-side Java NullPointerException.

See docs/API-NOTES.md for the full field conventions.
"""

from __future__ import annotations

import json
import sys
from typing import Any

import requests

from . import __version__
from .errors import SIGN_IN_HELP, ApiError, NotAuthenticated, SchemaDrift

API_BASE = "https://api.planbook.com"
AUTH_BASE = "https://auth.planbook.com"

# Honest identification. The ToS forbids forging identifiers to disguise
# origin, and nothing about this tool needs to look like a browser.
USER_AGENT = f"planbook-cli/{__version__} (+https://github.com/bryantclark/planbook-cli)"


def yn(value: bool) -> str:
    """Planbook booleans are the strings "Y" and "N"."""
    return "Y" if value else "N"


def intish(value: Any) -> str:
    """Integer fields must carry "0" when absent, never an empty string."""
    if value in (None, "", False):
        return "0"
    return str(int(value))


class PlanbookClient:
    """Authenticated client.

    Planbook's credential is a JWT. The browser sends it as a cookie named
    `U|<view-id>|.accesstoken`, but the server accepts a plain
    `Authorization: Bearer` header just as well - verified - so that is what
    this uses. The `SESSION` cookie plays no part in authentication.
    """

    def __init__(self, token: str, *, verbose: bool = False, timeout: int = 30):
        self.verbose = verbose
        self.timeout = timeout
        self.token = token
        self.http = requests.Session()
        self.http.headers["User-Agent"] = USER_AGENT
        self.http.headers["Authorization"] = f"Bearer {token}"

        # The token carries its own expiry, so a stale one can be caught here
        # rather than spending a round trip to be told the same thing.
        from . import token as _token

        if _token.is_expired(token):
            info = _token.describe(token)
            when = info.get("expires_in_hours")
            ago = f" (expired {abs(when)}h ago)" if isinstance(when, (int, float)) and when else ""
            raise NotAuthenticated(
                f"Your Planbook token has expired{ago}." + SIGN_IN_HELP
            )

    def post(self, path: str, data: dict[str, Any] | None = None) -> Any:
        """POST a form-encoded request and return the decoded body."""
        url = f"{API_BASE}/{path.lstrip('/')}"
        payload = {k: v for k, v in (data or {}).items() if v is not None}
        if self.verbose:
            keys = ",".join(sorted(payload)) or "-"
            print(f"POST {url} [{keys}]", file=sys.stderr)
        resp = self.http.post(url, data=payload, timeout=self.timeout)
        return self._check(resp, url)

    def _check(self, resp: requests.Response, url: str) -> Any:
        if resp.status_code == 405 and "awswaf" in resp.text.lower():
            raise SchemaDrift(
                f"{url} answered with an AWS WAF challenge. The API host is not "
                "normally behind the WAF - if this persists, Planbook has changed "
                "its edge configuration and this tool cannot proceed."
            )
        if resp.status_code >= 500:
            raise ApiError(f"{url} returned HTTP {resp.status_code}")

        text = resp.text.strip()
        if not text:
            return None
        try:
            body = json.loads(text)
        except ValueError:
            head = text[:200].replace("\n", " ")
            raise SchemaDrift(f"{url} returned non-JSON: {head!r}") from None

        if isinstance(body, dict):
            if str(body.get("notLoggedIn", "")).lower() == "true":
                raise NotAuthenticated(
                    "Your Planbook token was rejected - it has probably expired "
                    "(they last about 22 hours)." + SIGN_IN_HELP
                )
            if str(body.get("error", "")).lower() == "true":
                raise ApiError(body.get("msg") or f"{url} reported an unspecified error")
        return body

    def require(self, body: Any, *keys: str, where: str) -> dict:
        """Assert a response carries the keys we expect, or fail loudly.

        The API is undocumented; a silently-changed shape should stop the run
        rather than produce plausible wrong output.
        """
        if not isinstance(body, dict):
            raise SchemaDrift(f"{where}: expected an object, got {type(body).__name__}")
        missing = [k for k in keys if k not in body]
        if missing:
            raise SchemaDrift(
                f"{where}: response is missing {', '.join(missing)}. "
                "The API shape may have changed."
            )
        return body
