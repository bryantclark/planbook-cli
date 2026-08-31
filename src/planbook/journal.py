"""A durable record of what a bulk run wrote.

A bulk write is sent one lesson at a time, so an interrupted run leaves no
per-item result. Each item is recorded as it lands, keyed by class and date and
hashed on its payload, and `--resume` runs only the rest.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .contract import CONTRACT_VERSION
from .errors import UsageError
from .types import FormBody, Id, Result


def key_for(class_id: Id, date: str) -> str:
    """The identity of a lesson: `/updateLesson` is an upsert on class+date."""
    return f"{class_id}|{date}"


def payload_hash(payload: FormBody) -> str:
    """A stable hash of the request, so an edited item is not skipped."""
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(body.encode()).hexdigest()


class Journal:
    """Append-only record of one bulk run, readable by the next."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._done: dict[str, str] = {}

    def load(self) -> dict[str, str]:
        """Map of key -> payload hash for every item recorded as written."""
        if not self.path.exists():
            return {}
        done: dict[str, str] = {}
        for line in self.path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                # A torn line means "not written": the write is an upsert, so
                # running the item again is the safe direction.
                continue
            if isinstance(entry, dict) and entry.get("status") == "written":
                done[str(entry.get("key"))] = str(entry.get("payload_sha256"))
        self._done = done
        return done

    def already_written(self, key: str, digest: str) -> bool:
        return self._done.get(key) == digest

    def record(self, entry: Result) -> None:
        """Append one entry and flush it, so a crash keeps what came before."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as handle:
            json.dump({"contract": CONTRACT_VERSION, **entry}, handle, default=str)
            handle.write("\n")
            handle.flush()


def open_journal(path: str | None, *, resume: bool) -> Journal | None:
    """The journal for this run, if one was asked for."""
    if path is None:
        if resume:
            raise UsageError(
                "--resume needs --journal PATH: there is nothing to resume from "
                "without the record of what the interrupted run wrote."
            )
        return None
    journal = Journal(path)
    if resume:
        journal.load()
    return journal
