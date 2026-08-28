"""The Planbook access token.

Planbook authenticates API calls with a JWT, not with the `SESSION` cookie.
The browser carries it as a cookie named `U|<view-id>|.accesstoken`, but the
server also accepts it as a standard `Authorization: Bearer` header, which is
what this CLI uses.

The token is self-describing: its payload carries the account id, the current
school year id, the account's email, and an expiry. That lets `auth status`
say something useful without spending a request, and lets the CLI warn before
a token lapses instead of failing mid-run.
"""

from __future__ import annotations

import base64
import json
import re
import time
from typing import Any

# Matches the token wherever it appears: a bare JWT, a Cookie header, or a
# whole "Copy as cURL" paste.
COOKIE_RE = re.compile(r"\.accesstoken=([A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+)")
BEARER_RE = re.compile(r"[Bb]earer\s+([A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+)")
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
    """Decode the payload. Signature is not verified - only the server can.

    Planbook double-encodes: `sub` is itself a JSON string.
    """
    try:
        payload = json.loads(_b64(token.split(".")[1]))
    except Exception:
        return {}
    sub = payload.get("sub")
    if isinstance(sub, str):
        try:
            payload["sub"] = json.loads(sub)
        except ValueError:
            pass
    return payload


def describe(token: str) -> dict[str, Any]:
    """Human-facing summary of a token: who it is for and how long it lasts."""
    data = claims(token)
    sub = data.get("sub") or {}
    expires_at = data.get("exp")
    remaining = None
    if isinstance(expires_at, (int, float)):
        remaining = max(0, int(expires_at - time.time()))
    return {
        "account_id": sub.get("id") if isinstance(sub, dict) else None,
        "email": sub.get("email") if isinstance(sub, dict) else None,
        "year_id": sub.get("yearId") if isinstance(sub, dict) else None,
        "expires_at": expires_at,
        "expires_in_seconds": remaining,
        "expires_in_hours": round(remaining / 3600, 1) if remaining is not None else None,
        "expired": remaining == 0 if remaining is not None else None,
    }


def is_expired(token: str, *, skew: int = 60) -> bool:
    data = claims(token)
    expires_at = data.get("exp")
    if not isinstance(expires_at, (int, float)):
        return False  # no expiry claim: let the server decide
    return time.time() + skew >= expires_at
