"""Find the user's default browser, so sign-in opens the browser they use.

Only Chromium-family browsers can be driven here (Chrome, Brave, Edge, Vivaldi,
Opera, Arc). Firefox and Safari are not Chromium and cannot share the launch
path; if one of those is the default, we say so and fall back rather than
silently opening something else.
"""

from __future__ import annotations

import plistlib
import subprocess
import sys
from pathlib import Path

# Bundle identifier -> (display name, path to the executable inside the bundle)
CHROMIUM_BROWSERS = {
    "com.brave.browser": ("Brave", "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"),
    "com.brave.browser.beta": ("Brave Beta", "/Applications/Brave Browser Beta.app/Contents/MacOS/Brave Browser Beta"),
    "com.google.chrome": ("Chrome", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
    "com.google.chrome.canary": ("Chrome Canary", "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary"),
    "com.microsoft.edgemac": ("Edge", "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
    "com.vivaldi.vivaldi": ("Vivaldi", "/Applications/Vivaldi.app/Contents/MacOS/Vivaldi"),
    "com.operasoftware.opera": ("Opera", "/Applications/Opera.app/Contents/MacOS/Opera"),
    "company.thebrowser.browser": ("Arc", "/Applications/Arc.app/Contents/MacOS/Arc"),
    "com.thebrowser.dia": ("Dia", "/Applications/Dia.app/Contents/MacOS/Dia"),
}

# Defaults we recognise but cannot drive.
NON_CHROMIUM = {
    "org.mozilla.firefox": "Firefox",
    "com.apple.safari": "Safari",
    "org.mozilla.librewolf": "LibreWolf",
    "app.zen-browser.zen": "Zen",
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
            data = plistlib.load(fh)
    except Exception:
        # Falls back to `defaults`, which sometimes reads when plistlib cannot.
        try:
            out = subprocess.run(
                ["defaults", "read", "com.apple.LaunchServices/com.apple.launchservices.secure"],
                capture_output=True, text=True, timeout=10,
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

    for handler in data.get("LSHandlers", []):
        if handler.get("LSHandlerURLScheme") == "https":
            bundle = handler.get("LSHandlerRoleAll") or handler.get("LSHandlerRoleViewer")
            if bundle:
                return bundle.lower()
    return None


def default_chromium_executable() -> tuple[str, str] | None:
    """Return (name, executable_path) for the default browser if we can drive it.

    Returns None when the default is not Chromium-based, is not installed
    where expected, or cannot be determined.
    """
    bundle = default_browser_bundle_id()
    if not bundle:
        return None
    if bundle in NON_CHROMIUM:
        return None
    entry = CHROMIUM_BROWSERS.get(bundle)
    if not entry:
        return None
    name, executable = entry
    return (name, executable) if Path(executable).exists() else None


def default_browser_name() -> str | None:
    """Human-readable name of the default browser, driveable or not."""
    bundle = default_browser_bundle_id()
    if not bundle:
        return None
    if bundle in NON_CHROMIUM:
        return NON_CHROMIUM[bundle]
    if bundle in CHROMIUM_BROWSERS:
        return CHROMIUM_BROWSERS[bundle][0]
    return bundle
