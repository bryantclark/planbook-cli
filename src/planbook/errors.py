"""Error types. Every failure an agent can hit should be one of these.

Each carries the four things a caller has to branch on without reading prose:

  exit_code   what the process returns
  kind        a stable machine name, reported in the structured error
  retryable   whether running the same command again could succeed
  remedy      what to do about it

`planbook --error-json` prints that as one JSON object on stderr; the default
stays the human sentence. `planbook schema` lists the whole taxonomy.
"""

from __future__ import annotations

from .types import Result

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
    kind = "PlanbookError"
    retryable = False
    remedy = "Read the message; this failure has no standard remedy."

    def __init__(
        self,
        *args: object,
        remedy: str | None = None,
        retryable: bool | None = None,
        details: Result | None = None,
    ) -> None:
        super().__init__(*args)
        if remedy is not None:
            self.remedy = remedy
        if retryable is not None:
            self.retryable = retryable
        # What a caller needs to recover: records written, the failing
        # endpoint, the item index in a bulk run.
        self.details: Result = details or {}

    def to_dict(self) -> Result:
        from .contract import CONTRACT_VERSION

        error: Result = {
            "contract": CONTRACT_VERSION,
            "kind": self.kind,
            "code": self.exit_code,
            "retryable": self.retryable,
            "message": str(self),
            "remedy": self.remedy,
        }
        if self.details:
            error["details"] = self.details
        return {"error": error}


class NotAuthenticated(PlanbookError):
    """No session, or the stored session expired."""

    exit_code = 77  # EX_NOPERM
    kind = "NotAuthenticated"
    remedy = (
        "A human must sign in: open " + SIGN_IN_URL + " then run `planbook auth "
        "import`. Do not retry unattended."
    )


class LoginFailed(PlanbookError):
    exit_code = 77
    kind = "LoginFailed"
    remedy = NotAuthenticated.remedy


class ApiError(PlanbookError):
    """HTTP 200 with an error payload - Planbook signals failure in the body,
    not the status line, so this is the common case."""

    exit_code = 1
    kind = "ApiError"
    remedy = "Read the message. Check the ids you passed against a `list` call."


class Forbidden(PlanbookError):
    """HTTP 403. The token is valid but the account may not do this."""

    exit_code = 1
    kind = "Forbidden"
    remedy = (
        "The session is real but not allowed here. Do not retry: check the ids "
        "belong to this account, and that the plan covers the feature."
    )


class RateLimited(PlanbookError):
    """HTTP 429. Planbook is asking for a pause, and says how long for."""

    exit_code = 1
    kind = "RateLimited"
    retryable = True
    remedy = (
        "Wait `details.retry_after` seconds - the server named it - then send "
        "the same request once. Do not retry in a loop."
    )


class TransportError(PlanbookError):
    """The request never got a usable answer: DNS, TLS, timeout, 5xx."""

    exit_code = 1
    kind = "TransportError"
    retryable = True
    remedy = (
        "Transient. Retry once after 30s - not in a loop; Planbook reserves "
        "rate limits. If it persists, treat Planbook as down."
    )


class SchemaDrift(PlanbookError):
    """A response was not the shape this CLI expects. Raised rather than
    returning half-parsed data: the API is undocumented and can change."""

    exit_code = 65  # EX_DATAERR
    kind = "SchemaDrift"
    remedy = (
        "Stop. Do not retry and do not improvise a workaround - the API shape "
        "changed and this tool cannot tell right from wrong output. Report it."
    )


class UsageError(PlanbookError):
    exit_code = 64  # EX_USAGE
    kind = "UsageError"
    remedy = "Fix the arguments. `planbook schema` lists every flag and its type."


class Ambiguous(ApiError):
    """A write succeeded but its record could not be identified. The work was
    done, so retrying would duplicate it."""

    exit_code = 1
    kind = "Ambiguous"
    remedy = (
        "The write went through - do NOT retry, you would create a duplicate. "
        "Run the matching `list` command to find the record."
    )


class PostconditionFailed(ApiError):
    """The server accepted the write and did not store it. Planbook answers
    HTTP 200 either way, so every write is read back."""

    exit_code = 1
    kind = "PostconditionFailed"
    remedy = (
        "The server reported success but stored nothing. Re-read the record "
        "before retrying; check the ids and that the date is in the class's range."
    )


#: Every error kind, for `planbook schema`.
ERROR_KINDS: tuple[type[PlanbookError], ...] = (
    UsageError,
    ApiError,
    TransportError,
    SchemaDrift,
    NotAuthenticated,
    LoginFailed,
    Forbidden,
    RateLimited,
    Ambiguous,
    PostconditionFailed,
)
