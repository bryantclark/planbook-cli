"""Error types. Every failure an agent can hit should be one of these."""


class PlanbookError(Exception):
    """Base class. Carries an exit code so the CLI can map errors to shells."""

    exit_code = 1


class NotAuthenticated(PlanbookError):
    """No session, or the stored session expired."""

    exit_code = 77  # EX_NOPERM


class LoginFailed(PlanbookError):
    exit_code = 77


class ApiError(PlanbookError):
    """The API returned HTTP 200 with an error payload.

    Planbook signals failure in the body, not the status line, so this is the
    common case rather than the exceptional one.
    """

    exit_code = 1


class SchemaDrift(PlanbookError):
    """A response did not look the way this CLI expects.

    Raised loudly rather than returning half-parsed data: the API is
    undocumented and can change without notice.
    """

    exit_code = 65  # EX_DATAERR


class UsageError(PlanbookError):
    exit_code = 64  # EX_USAGE
