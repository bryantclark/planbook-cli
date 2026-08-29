"""HTTP client for the Planbook private API.

Three API facts drive the design:

1.  Failure arrives as HTTP 200 with an error body, so every response goes
    through :meth:`_check`.
2.  Every call is a form-encoded POST; there is no JSON body and no other verb.
3.  Integer-typed fields must carry "0" when absent - "" raises a server-side
    Java NullPointerException.

See docs/API-NOTES.md for the full field conventions.
"""

from __future__ import annotations

import json
import mimetypes
import sys
import time
from pathlib import Path
from typing import Any

import requests

from . import __version__
from .errors import SIGN_IN_HELP, ApiError, NotAuthenticated, SchemaDrift
from .wire import intish as intish
from .wire import yn as yn

API_BASE = "https://api.planbook.com"
AUTH_BASE = "https://auth.planbook.com"

# Honest identification: the ToS forbids disguising origin, and nothing here
# needs to look like a browser.
USER_AGENT = (
    f"planbook-cli/{__version__} (+https://github.com/bryantclark/planbook-cli)"
)


class PlanbookClient:
    """Authenticated client.

    The credential is the `U|<view-id>|.accesstoken` JWT, sent as
    `Authorization: Bearer`. The `SESSION` cookie authenticates nothing.
    """

    def __init__(self, token: str, *, verbose: bool = False, timeout: int = 30):
        self.verbose = verbose
        self.timeout = timeout
        self.token = token
        self.http = requests.Session()
        self.http.headers["User-Agent"] = USER_AGENT
        self.http.headers["Authorization"] = f"Bearer {token}"

        # The token carries its own expiry, so catch a stale one here instead
        # of spending a round trip to be told the same thing.
        from . import token as _token

        if _token.is_expired(token):
            expires_at = _token.claims(token).get("exp")
            ago = ""
            if isinstance(expires_at, (int, float)):
                hours = (time.time() - expires_at) / 3600
                if hours >= 0.1:
                    ago = f" (expired {hours:.1f}h ago)"
            raise NotAuthenticated(
                f"Your Planbook token has expired{ago}." + SIGN_IN_HELP
            )

    def post(self, path: str, data: dict[str, Any] | None = None) -> Any:
        url = f"{API_BASE}/{path.lstrip('/')}"
        payload = {k: v for k, v in (data or {}).items() if v is not None}
        if self.verbose:
            keys = ",".join(sorted(payload)) or "-"
            print(f"POST {url} [{keys}]", file=sys.stderr)
        resp = self.http.post(url, data=payload, timeout=self.timeout)
        return self._check(resp, url)

    def upload(self, path: str, file_path: str) -> Any:
        """POST a file as multipart. `/uploadAttachment` is the only such endpoint."""
        url = f"{API_BASE}/{path.lstrip('/')}"
        name = Path(file_path).name
        # The part must carry a content type: without one the server fails
        # with `Cannot invoke "String.indexOf(String)" because "fileType" is
        # null`, which says nothing about the real cause.
        content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
        if self.verbose:
            print(f"POST {url} [multipart: {name} ({content_type})]", file=sys.stderr)
        with Path(file_path).open("rb") as handle:
            resp = self.http.post(
                url,
                files={"file": (name, handle, content_type)},
                timeout=max(self.timeout, 120),
            )
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
                raise ApiError(
                    body.get("msg") or f"{url} reported an unspecified error"
                )
        return body

    def require(self, body: Any, *keys: str, where: str) -> dict[str, Any]:
        """Require the keys we expect. The API is undocumented, so a changed
        shape should stop the run rather than produce plausible wrong output.
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
