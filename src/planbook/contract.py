"""The machine contract this CLI publishes.

Bump `CONTRACT_VERSION` whenever the *shape* of anything an agent parses
changes: the success envelope, the structured error object, the `schema`
manifest, or the dry-run preview. Adding a command or a flag is a minor bump;
renaming or removing a documented key is a major one.

`planbook schema` reports the version.
"""

from __future__ import annotations

CONTRACT_MAJOR = 1
CONTRACT_MINOR = 6
CONTRACT_VERSION = f"{CONTRACT_MAJOR}.{CONTRACT_MINOR}"

EXIT_CODES: dict[int, dict[str, str]] = {
    0: {"meaning": "success", "action": "parse stdout as JSON"},
    1: {"meaning": "api error", "action": "read the structured error"},
    64: {"meaning": "usage error", "action": "fix the arguments"},
    65: {
        "meaning": "unexpected response shape",
        "action": "stop; do not retry or improvise",
    },
    77: {
        "meaning": "not authenticated",
        "action": "relay the remedy to a human and stop",
    },
    130: {"meaning": "interrupted", "action": "none"},
}
