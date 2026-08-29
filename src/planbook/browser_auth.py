"""Sign in by driving a real browser window.

`auth.py` only handles Planbook's own username/password; SSO accounts
(Google, Microsoft, Clever, ClassLink, Apple) cannot and should not be driven
that way. So this opens a browser, lets the human sign in, and takes the
access token once one appears in the jar. We never see the password.

Chrome is launched by channel rather than Playwright's bundled Chromium: no
150MB download, and identity providers refuse OAuth in an automation browser.
"""

from __future__ import annotations

import contextlib
import sys
import time
from pathlib import Path
from typing import Any, cast

from .config import config_dir
from .default_browser import (
    default_browser_name,
    default_chromium_executable,
)
from .errors import LoginFailed

# The app host mints the access token, so sign-in must end up there. The WAF
# challenges headless only (headed Brave 200, headless 405), which is why
# interactive sign-in works and a silent headless refresh may not.
SIGNIN_URL = "https://app.planbook.com/"
# The cookie is `U|<view-id>|.accesstoken`; the view id varies per session, so
# match on the suffix.
TOKEN_COOKIE_SUFFIX = ".accesstoken"

# Fallback launch channels, in order.
CHANNELS = ("chrome", "msedge", "chromium")


def default_profile_dir() -> Path:
    return config_dir() / "browser-profile"


def _import_playwright() -> Any:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise LoginFailed(
            "Browser sign-in needs Playwright, which is not installed.\n"
            "  pip install 'planbook-cli[browser]'\n"
            "Prefer `planbook auth import`, which reads the token from a "
            "browser you are already signed in to and needs no extra install."
        ) from exc
    return sync_playwright


def login_via_browser(
    *,
    timeout: int = 300,
    channel: str | None = None,
    profile: Path | None = None,
    headless: bool = False,
    quiet: bool = False,
) -> str:
    """Open a browser, wait for the user to sign in, return an access token.

    Polls the cookie jar rather than watching for a URL: the sign-in path
    differs per identity provider, and all that matters is whether the token
    works. `headless` cannot be interacted with, so it only pays off once the
    stored profile already holds a signed-in session.
    """
    sync_playwright = _import_playwright()
    from .auth import _works  # local import: avoids a cycle at module load

    profile_dir = profile or default_profile_dir()
    profile_dir.mkdir(parents=True, exist_ok=True)
    profile_dir.chmod(0o700)

    tested: set[str] = set()

    # Prefer the user's own browser: their identity provider session lives
    # there, and an unfamiliar sign-in window is its own small hazard.
    preferred: list[tuple[str, dict[str, Any]]] = []
    if not channel:
        found = default_chromium_executable()
        if found:
            name, executable = found
            preferred.append((name, {"executable_path": executable}))
    channels = (channel,) if channel else CHANNELS
    for candidate in channels:
        preferred.append(
            (
                candidate,
                {} if candidate == "chromium" else {"channel": candidate},
            )
        )

    with sync_playwright() as pw:
        context = None
        last_error: Exception | None = None
        launched = None
        for label, launch_kwargs in preferred:
            try:
                context = pw.chromium.launch_persistent_context(
                    str(profile_dir),
                    headless=headless,
                    args=["--no-first-run", "--no-default-browser-check"],
                    **launch_kwargs,
                )
                launched = label
                break
            except Exception as exc:  # not installed on this machine
                last_error = exc
        if context is None:
            tried = ", ".join(label for label, _ in preferred)
            hint = ""
            browser_name = default_browser_name()
            if browser_name and not default_chromium_executable():
                hint = (
                    f"\nYour default browser is {browser_name}, which is not Chromium-based "
                    "and cannot be driven here. A Chromium browser (Chrome, Brave, "
                    "Edge) is needed, or use `planbook auth cookie` instead."
                )
            raise LoginFailed(
                f"Could not launch a browser (tried {tried}). "
                f"Last error: {last_error}{hint}\n"
                "You can also run `playwright install chromium`."
            )

        if not quiet:
            print(
                f"Opening {launched}. Sign in to Planbook however you normally do "
                "(Google is fine).\nThis window closes by itself once you are in.",
                file=sys.stderr,
            )

        # The browser makes its own first page, but not always before launch()
        # returns; calling new_page() now would leave a stray about:blank tab.
        page = None
        for _ in range(20):  # up to ~4s
            if context.pages:
                page = context.pages[0]
                break
            time.sleep(0.2)
        if page is None:
            page = context.new_page()

        # A slow or redirected load is not fatal; the poll loop decides.
        with contextlib.suppress(Exception):
            page.goto(SIGNIN_URL, timeout=60_000)

        # Safe to close: this profile is ours alone, nothing here is the user's.
        for other in list(context.pages):
            if other is page:
                continue
            with contextlib.suppress(Exception):
                if other.url in ("about:blank", "") or other.url.startswith(
                    (
                        "chrome://welcome",
                        "brave://welcome",
                        "chrome://new-tab-page",
                    )
                ):
                    other.close()

        if not headless:
            with contextlib.suppress(Exception):
                page.bring_to_front()

        deadline = time.time() + timeout
        try:
            while time.time() < deadline:
                if not headless and not context.pages:
                    raise LoginFailed("Browser was closed before sign-in completed.")

                for cookie in context.cookies():
                    name = cookie.get("name") or ""
                    value = cast(str | None, cookie.get("value"))
                    if not value or not name.endswith(TOKEN_COOKIE_SUFFIX):
                        continue
                    if value in tested:
                        continue
                    tested.add(value)
                    # Confirm it works the way the CLI will use it: a Bearer
                    # header, no cookies, no browser.
                    if _works(value):
                        return value

                time.sleep(2)
        finally:
            with contextlib.suppress(Exception):
                context.close()

    raise LoginFailed(
        f"No working session appeared within {timeout}s. "
        "Run again with --timeout to allow longer."
    )


def refresh_or_login(
    *,
    timeout: int = 300,
    channel: str | None = None,
    profile: Path | None = None,
) -> tuple[str, bool]:
    """Kept for API compatibility; always signs in interactively.

    A silent headless refresh is not possible: the token is minted on
    app.planbook.com, whose WAF challenges headless browsers. Only a headed
    window gets through, and that needs a person.
    """
    return login_via_browser(
        timeout=timeout, channel=channel, profile=profile, headless=False
    ), True
