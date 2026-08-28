"""Error types. Every failure an agent can hit should be one of these."""

SIGN_IN_URL = "https://app.planbook.com/"

# One copy, so every not-signed-in path gives the identical remedy.
SIGN_IN_HELP = (
    f"\n\n  1. Open {SIGN_IN_URL} and sign in\n"
    "  2. Run: planbook auth import\n\n"
    "`auth import` reads the token from the browser you signed in with. "
    "If macOS asks for Keychain access, choose Always Allow."
)


class PlanbookError(Exception):
    """Base class. Carries the exit code the CLI returns for this failure."""

    exit_code = 1


class NotAuthenticated(PlanbookError):
    """No session, or the stored session expired."""

    exit_code = 77  # EX_NOPERM


class LoginFailed(PlanbookError):
    exit_code = 77


class ApiError(PlanbookError):
    """HTTP 200 with an error payload - Planbook signals failure in the body,
    not the status line, so this is the common case."""

    exit_code = 1


class SchemaDrift(PlanbookError):
    """A response did not look the way this CLI expects. Raised rather than
    returning half-parsed data: the API is undocumented and can change."""

    exit_code = 65  # EX_DATAERR


class UsageError(PlanbookError):
    exit_code = 64  # EX_USAGE
