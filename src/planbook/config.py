"""Where the session lives on disk."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .errors import SIGN_IN_HELP, NotAuthenticated

APP_NAME = "planbook"
TOKEN_ENV = "PLANBOOK_TOKEN"


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".config"
    return root / APP_NAME


def session_path() -> Path:
    return config_dir() / "token.json"


def save_session(token: str, username: str | None = None) -> Path:
    d = config_dir()
    d.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = session_path()
    payload = {"token": token, "username": username}
    # Written 0600: this token is a bearer credential for the whole account.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        json.dump(payload, fh)
    # O_CREAT's mode applies only on creation; an existing looser file keeps
    # its permissions without this.
    path.chmod(0o600)
    return path


def load_session() -> str:
    """Return the access token, preferring the environment over disk."""
    env = os.environ.get(TOKEN_ENV)
    if env:
        return env.strip()
    path = session_path()
    if not path.exists():
        raise NotAuthenticated("Not signed in." + SIGN_IN_HELP)
    try:
        data = json.loads(path.read_text())
        token = data["token"]
        if not isinstance(token, str) or not token:
            raise ValueError("`token` is not a non-empty string")
        return token
    except (ValueError, KeyError, TypeError, OSError) as exc:
        raise NotAuthenticated(f"Token file at {path} is unreadable: {exc}") from exc


def clear_session() -> bool:
    path = session_path()
    if path.exists():
        path.unlink()
        return True
    return False
