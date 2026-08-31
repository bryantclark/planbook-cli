"""Name the user's default browser (macOS only)."""

from __future__ import annotations

import plistlib
import subprocess
import sys
from pathlib import Path
from typing import cast

# Bundle identifier -> display name. The first word is matched against
# browser_cookies.KNOWN_BROWSERS, so "Brave Beta" resolves to "brave".
BROWSER_NAMES = {
    "com.brave.browser": "Brave",
    "com.brave.browser.beta": "Brave Beta",
    "com.google.chrome": "Chrome",
    "com.google.chrome.canary": "Chrome Canary",
    "com.microsoft.edgemac": "Edge",
    "com.vivaldi.vivaldi": "Vivaldi",
    "com.operasoftware.opera": "Opera",
    "company.thebrowser.browser": "Arc",
    "com.thebrowser.dia": "Dia",
    "org.mozilla.firefox": "Firefox",
    "org.mozilla.librewolf": "LibreWolf",
    "app.zen-browser.zen": "Zen",
    "com.apple.safari": "Safari",
}

_PLIST = (
    "~/Library/Preferences/com.apple.LaunchServices/"
    "com.apple.launchservices.secure.plist"
)


def default_browser_bundle_id() -> str | None:
    """Return the bundle id handling https:// , or None if it cannot be read."""
    if sys.platform != "darwin":
        return None
    path = Path(_PLIST).expanduser()
    try:
        with path.open("rb") as fh:
            data = cast("dict[str, object]", plistlib.load(fh))
    except Exception:
        # Falls back to `defaults`, which sometimes reads when plistlib cannot.
        try:
            out = subprocess.run(
                [
                    "defaults",
                    "read",
                    "com.apple.LaunchServices/com.apple.launchservices.secure",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            ).stdout
        except Exception:
            return None
        marker = '"https"'
        if marker not in out:
            return None
        # Crude but adequate: the handler is listed just above its scheme.
        chunk = out.split(marker)[0].rsplit("LSHandlerRoleAll", 1)
        if len(chunk) < 2:
            return None
        return chunk[1].split('"')[1].lower() if '"' in chunk[1] else None

    handlers = data.get("LSHandlers")
    for handler in handlers if isinstance(handlers, list) else []:
        if not isinstance(handler, dict):
            continue
        if handler.get("LSHandlerURLScheme") == "https":
            bundle = handler.get("LSHandlerRoleAll") or handler.get(
                "LSHandlerRoleViewer"
            )
            if bundle:
                return cast(str, bundle.lower())
    return None


def default_browser_name() -> str | None:
    bundle = default_browser_bundle_id()
    if not bundle:
        return None
    return BROWSER_NAMES.get(bundle, bundle)
