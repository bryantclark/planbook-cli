"""Sign in by driving a real browser window.

The form login in `auth.py` only handles Planbook's own username/password.
Accounts that sign in with Google, Microsoft, Clever, ClassLink, or Apple
cannot be driven that way - and should not be, since it would mean handling
somebody else's identity provider credentials.

So this does the honest thing: it opens a browser, hands it to the person at
the keyboard, and waits. The human signs in however their account works. We
never see the password. When a working `SESSION` cookie appears in the jar,
we take that and close the window.

Chrome is launched by channel rather than using Playwright's bundled
Chromium, for two reasons: no 150MB browser download, and identity providers
routinely refuse to complete OAuth in a bundled automation browser.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from .config import config_dir
from .errors import LoginFailed

# Sign in on the auth host, never the app host. app.planbook.com sits behind
# an AWS WAF that challenges any automated browser (verified: HTTP 405,
# "Human Verification"). auth.planbook.com has no such protection, and it is
# where the login form and every SSO button actually live. Routing here is
# using the unprotected endpoint, not evading the protected one.
SIGNIN_URL = "https://auth.planbook.com/login"
API_PROBE = "https://api.planbook.com/getClasses2"

# Channels to try, in order. Real installed browsers first.
CHANNELS = ("chrome", "msedge", "chromium")


def default_profile_dir() -> Path:
    return config_dir() / "browser-profile"


def _import_playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise LoginFailed(
            "Browser sign-in needs Playwright, which is not installed.\n"
            "  pip install 'planbook-cli[browser]'\n"
            "Alternatively, copy the SESSION cookie out of your browser's "
            "DevTools and run `planbook auth cookie`."
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
    """Open a browser, wait for the user to sign in, return a SESSION cookie.

    Polls the cookie jar rather than watching for a particular URL, because
    the sign-in path differs per identity provider and the only thing that
    actually matters is whether the resulting cookie works against the API.

    With `headless`, no window is shown and nobody can interact - only useful
    once the profile already holds a signed-in session. That is the whole
    point of keeping the profile: the first sign-in is interactive, every
    refresh afterwards is silent.
    """
    sync_playwright = _import_playwright()
    from .auth import _works  # local import: avoids a cycle at module load

    profile_dir = profile or default_profile_dir()
    profile_dir.mkdir(parents=True, exist_ok=True)
    profile_dir.chmod(0o700)

    channels = (channel,) if channel else CHANNELS
    tested: set[str] = set()

    with sync_playwright() as pw:
        context = None
        last_error: Exception | None = None
        for candidate in channels:
            try:
                context = pw.chromium.launch_persistent_context(
                    str(profile_dir),
                    headless=headless,
                    channel=candidate if candidate != "chromium" else None,
                    args=["--no-first-run", "--no-default-browser-check"],
                )
                break
            except Exception as exc:  # channel not installed on this machine
                last_error = exc
        if context is None:
            raise LoginFailed(
                f"Could not launch a browser (tried {', '.join(channels)}). "
                f"Last error: {last_error}\n"
                "If you have no Chrome or Edge, run `playwright install chromium`."
            )

        if not quiet:
            print(
                "Opening a browser. Sign in to Planbook however you normally do "
                "(Google is fine).\nThis window closes by itself once you are in.",
                file=sys.stderr,
            )

        page = context.pages[0] if context.pages else context.new_page()
        try:
            page.goto(SIGNIN_URL, timeout=60_000)
        except Exception:
            pass  # a slow or redirected load is not fatal; keep polling

        deadline = time.time() + timeout
        try:
            while time.time() < deadline:
                if not headless and not context.pages:
                    raise LoginFailed("Browser was closed before sign-in completed.")

                # Ask the API, from inside the browser, using the browser's own
                # cookie jar. This does two jobs at once: it tells us whether
                # the sign-in has taken effect, and it makes the server issue
                # an api-host SESSION cookie if the auth-host session
                # propagates. Guessing which cookie to try would not do that.
                try:
                    resp = context.request.post(API_PROBE, timeout=15_000)
                    body = resp.json()
                    signed_in = (
                        isinstance(body, dict)
                        and str(body.get("notLoggedIn", "")).lower() != "true"
                    )
                except Exception:
                    signed_in = False

                if signed_in:
                    for cookie in context.cookies():
                        value = cookie.get("value")
                        if cookie.get("name") != "SESSION" or not value:
                            continue
                        if value in tested:
                            continue
                        tested.add(value)
                        # Confirm the cookie works on its own, outside the
                        # browser - that is how the CLI will use it.
                        if _works(value):
                            return value

                time.sleep(2)
        finally:
            try:
                context.close()
            except Exception:
                pass

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
    """Try a silent refresh first, then fall back to interactive sign-in.

    Returns (cookie, was_interactive). The silent attempt is short: if the
    stored profile still holds a live sign-in, Planbook hands over a session
    almost immediately, and if it does not there is nothing to wait for.
    """
    profile_dir = profile or default_profile_dir()
    if profile_dir.exists():
        try:
            cookie = login_via_browser(
                timeout=25,
                channel=channel,
                profile=profile_dir,
                headless=True,
                quiet=True,
            )
            return cookie, False
        except LoginFailed:
            pass  # profile is stale or empty; fall through to interactive
    return login_via_browser(
        timeout=timeout, channel=channel, profile=profile_dir, headless=False
    ), True
