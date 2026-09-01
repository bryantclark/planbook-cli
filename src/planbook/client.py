"""HTTP client for the Planbook private API.

Three API facts drive the design:

1.  Failure arrives as HTTP 200 with an error body, so every response goes
    through :meth:`_check`.
2.  Most calls are a form-encoded POST; a `/services/planbook/**` family is
    GET-only (:meth:`get`) and a few endpoints want a JSON body
    (:meth:`post_json`).
3.  Integer-typed fields must carry "0" when absent - "" raises a server-side
    Java NullPointerException.

See docs/API-NOTES.md for the full field conventions.
"""

from __future__ import annotations

import json
import math
import mimetypes
import sys
import time
from datetime import timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests

from . import __version__
from .errors import (
    SIGN_IN_HELP,
    ApiError,
    Forbidden,
    NotAuthenticated,
    RateLimited,
    SchemaDrift,
    TransportError,
)
from .narrow import flag
from .types import FormBody, JsonObject, JsonValue

API_BASE = "https://api.planbook.com"

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

        # The token carries its own expiry: no round trip needed to spot a
        # stale one.
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

    def post(self, path: str, data: FormBody | None = None) -> JsonValue:
        url = f"{API_BASE}/{path.lstrip('/')}"
        payload = dict(data or {})
        if self.verbose:
            keys = ",".join(sorted(payload)) or "-"
            print(f"POST {url} [{keys}]", file=sys.stderr)
        resp = self.http.post(url, data=payload, timeout=self.timeout)
        return self._check(resp, url)

    def get(self, path: str, params: FormBody | None = None) -> JsonValue:
        """GET a service endpoint.

        `/services/planbook/**` answers only to GET; a POST there comes back
        `{"error":"true","message":"HTTP 405 Method Not Allowed"}`.
        """
        url = f"{API_BASE}/{path.lstrip('/')}"
        query = dict(params or {})
        if self.verbose:
            keys = ",".join(sorted(query)) or "-"
            print(f"GET {url} [{keys}]", file=sys.stderr)
        resp = self.http.get(url, params=query, timeout=self.timeout)
        return self._check(resp, url)

    def post_json(self, path: str, body: JsonObject | None = None) -> JsonValue:
        """POST a JSON body.

        A few service endpoints reject form encoding with `A JSONObject text
        must begin with '{'`.
        """
        url = f"{API_BASE}/{path.lstrip('/')}"
        if self.verbose:
            print(f"POST {url} [json]", file=sys.stderr)
        resp = self.http.post(url, json=body or {}, timeout=self.timeout)
        return self._check(resp, url)

    def upload(self, path: str, file_path: str) -> JsonValue:
        """POST a file as multipart. `/uploadAttachment` is the only such endpoint."""
        url = f"{API_BASE}/{path.lstrip('/')}"
        name = Path(file_path).name
        # Without a content type the server fails with `Cannot invoke
        # "String.indexOf(String)" because "fileType" is null`.
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

    def _check(self, resp: requests.Response, url: str) -> JsonValue:
        if resp.status_code in (403, 405) and "awswaf" in resp.text.lower():
            raise SchemaDrift(
                f"{url} answered with an AWS WAF challenge. Planbook has "
                "changed its edge configuration; this tool cannot proceed."
            )
        if resp.status_code == 401:
            raise NotAuthenticated(
                f"{url} rejected the token (HTTP 401)." + SIGN_IN_HELP
            )
        if resp.status_code == 403:
            raise Forbidden(f"{url} refused this account (HTTP 403).")
        if resp.status_code == 429:
            wait = retry_after(resp.headers.get("Retry-After"))
            raise RateLimited(
                f"{url} is rate limiting this account (HTTP 429). "
                + (
                    f"It asks for {wait}s."
                    if wait is not None
                    else "It did not say for how long."
                ),
                details={"endpoint": url, "retry_after": wait},
            )
        if resp.status_code >= 500:
            # Transient, so retryable - unlike an error reported in a 200 body.
            raise TransportError(f"{url} returned HTTP {resp.status_code}")

        text = resp.text.strip()
        if not text:
            return None
        try:
            body: JsonValue = json.loads(text)
        except ValueError:
            head = text[:200].replace("\n", " ")
            raise SchemaDrift(f"{url} returned non-JSON: {head!r}") from None

        if isinstance(body, dict):
            if flag(body.get("notLoggedIn")):
                raise NotAuthenticated(
                    "Your Planbook token was rejected - it has probably expired "
                    "(they last about 22 hours, or 1 hour for auth-server tokens)."
                    + SIGN_IN_HELP
                )
            if flag(body.get("error")):
                detail = body.get("msg") or body.get("message")
                if detail and "405" in str(detail):
                    detail = f"{detail} - GET-only endpoint; try `raw --get`"
                raise ApiError(
                    f"{url}: {detail}" if detail else f"{url} reported an error"
                )
        return body

    def require(self, body: JsonValue, *keys: str, where: str) -> JsonObject:
        """Require the keys we expect, so drift stops the run."""
        if not isinstance(body, dict):
            raise SchemaDrift(f"{where}: expected an object, got {type(body).__name__}")
        missing = [k for k in keys if k not in body]
        if missing:
            raise SchemaDrift(
                f"{where}: response is missing {', '.join(missing)}. "
                "The API shape may have changed."
            )
        return body


def retry_after(header: str | None) -> int | None:
    """`Retry-After` as whole seconds. It is either a count or an HTTP date."""
    if not header:
        return None
    value = header.strip()
    if value.isdigit():
        return int(value)
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return max(0, math.ceil(when.timestamp() - time.time()))
