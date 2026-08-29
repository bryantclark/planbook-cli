"""The Planbook access token.

Planbook authenticates with a JWT, not with the `SESSION` cookie. The browser
carries it as a cookie named `U|<view-id>|.accesstoken`; the server also
accepts it as `Authorization: Bearer`, which is what this CLI sends.

The payload carries account id, year id, email and expiry, so `auth status`
and expiry warnings cost no request.
"""

from __future__ import annotations

import base64
import contextlib
import json
import re
import time
from typing import Any

# The token turns up as a bare JWT, inside a Cookie header, or in a whole
# "Copy as cURL" paste.
COOKIE_RE = re.compile(
    r"\.accesstoken=([A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+)"
)
BEARER_RE = re.compile(
    r"[Bb]earer\s+([A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+)"
)
JWT_RE = re.compile(r"^[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+$")


def extract(text: str) -> str | None:
    """Pull an access token out of whatever was pasted."""
    text = text.strip()
    if JWT_RE.match(text):
        return text
    for pattern in (COOKIE_RE, BEARER_RE):
        match = pattern.search(text)
        if match:
            return match.group(1)
    return None


def _b64(segment: str) -> bytes:
    return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))


def claims(token: str) -> dict[str, Any]:
    """Decode the payload; the signature is not verified - only the server can.

    Planbook double-encodes: `sub` is itself a JSON string.
    """
    try:
        payload = json.loads(_b64(token.split(".")[1]))
    except Exception:
        return {}
    sub = payload.get("sub")
    if isinstance(sub, str):
        with contextlib.suppress(ValueError):
            payload["sub"] = json.loads(sub)
    return payload


def describe(token: str) -> dict[str, Any]:
    """Who the token is for and how long it lasts."""
    data = claims(token)
    sub = data.get("sub")
    if not isinstance(sub, dict):
        sub = {}
    expires_at = data.get("exp")
    remaining = None
    if isinstance(expires_at, (int, float)):
        remaining = max(0, int(expires_at - time.time()))
    return {
        "account_id": sub.get("id"),
        "email": sub.get("email"),
        "year_id": sub.get("yearId"),
        "expires_at": expires_at,
        "expires_in_seconds": remaining,
        "expires_in_hours": round(remaining / 3600, 1)
        if remaining is not None
        else None,
        "expired": remaining == 0 if remaining is not None else None,
    }


def is_expired(token: str, *, skew: int = 60) -> bool:
    data = claims(token)
    expires_at = data.get("exp")
    if not isinstance(expires_at, (int, float)):
        return False  # no expiry claim: let the server decide
    return time.time() + skew >= expires_at
