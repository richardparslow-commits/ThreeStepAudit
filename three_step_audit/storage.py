"""Durable draft storage for ThreeStepAudit.

Drafts are keyed by a per-visitor id so two people using the same deployment
cannot overwrite each other's work. The id is a capability token: it lives in
the visitor's URL, which is what makes a draft survive a refresh and an app
restart. It is not authentication — anyone holding the link can edit that draft.

The store is deliberately local SQLite (stdlib): it is the seam to swap for a
shared database once audits have owners and sign-in.
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from three_step_audit.workflow import Workflow

#: Key used by the pre-isolation, single-slot version of this app.
LEGACY_ID = "current"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "var" / "three_step_audit.sqlite3"
ENV_DB_PATH = "THREESTEPAUDIT_DB"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS drafts (
    id TEXT PRIMARY KEY,
    payload TEXT NOT NULL,
    saved_at TEXT NOT NULL
)
"""


class DraftStoreError(RuntimeError):
    """Raised when the draft database cannot be read or written."""


class DraftStore:
    """Per-visitor drafts, persisted as JSON in SQLite.

    ``db_path`` defaults to ``var/three_step_audit.sqlite3`` beside the app, and
    can be overridden with the ``THREESTEPAUDIT_DB`` environment variable.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path is not None else self._default_path()

    @staticmethod
    def _default_path() -> Path:
        override = os.environ.get(ENV_DB_PATH)
        return Path(override).expanduser() if override else DEFAULT_DB_PATH

    @contextmanager
    def _session(self) -> Iterator[sqlite3.Connection]:
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self.db_path, timeout=5.0)
            conn.row_factory = sqlite3.Row
            conn.execute(_SCHEMA)
            conn.commit()
        except (OSError, sqlite3.Error) as exc:
            raise DraftStoreError(f"cannot open the draft database: {exc}") from exc

        try:
            with conn:
                yield conn
        except sqlite3.Error as exc:
            raise DraftStoreError(f"draft database error: {exc}") from exc
        finally:
            conn.close()

    @staticmethod
    def _check_id(draft_id: str) -> str:
        if not isinstance(draft_id, str) or not draft_id.strip():
            raise ValueError("a draft id is required")
        return draft_id

    def save(self, draft_id: str, workflow: Workflow) -> datetime:
        """Write one visitor's draft and return when it was saved."""
        draft_id = self._check_id(draft_id)
        saved_at = datetime.now(timezone.utc)
        payload = workflow.to_json()
        with self._session() as conn:
            conn.execute(
                "INSERT INTO drafts (id, payload, saved_at) VALUES (?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET payload = excluded.payload, "
                "saved_at = excluded.saved_at",
                (draft_id, payload, saved_at.isoformat()),
            )
        return saved_at

    def load(self, draft_id: str) -> Workflow | None:
        """Return one visitor's draft, or ``None`` if they have not saved yet.

        Raises :class:`ValueError` if the stored payload is not a readable draft.
        """
        draft_id = self._check_id(draft_id)
        with self._session() as conn:
            row = conn.execute(
                "SELECT payload FROM drafts WHERE id = ?", (draft_id,)
            ).fetchone()
        if row is None:
            return None
        return Workflow.from_json(row["payload"])

    def saved_at(self, draft_id: str) -> datetime | None:
        draft_id = self._check_id(draft_id)
        with self._session() as conn:
            row = conn.execute(
                "SELECT saved_at FROM drafts WHERE id = ?", (draft_id,)
            ).fetchone()
        if row is None:
            return None
        return datetime.fromisoformat(row["saved_at"])

    def clear(self, draft_id: str) -> bool:
        """Remove one visitor's draft; returns whether there was one to remove."""
        draft_id = self._check_id(draft_id)
        with self._session() as conn:
            deleted = conn.execute(
                "DELETE FROM drafts WHERE id = ?", (draft_id,)
            ).rowcount
        return deleted > 0

    def load_for_visitor(self, draft_id: str) -> Workflow | None:
        """This visitor's draft, taking over the old single-slot draft if needed.

        Before drafts were per-visitor there was one shared slot. On the first
        visit after that change, whoever arrives next inherits it and the legacy
        slot is removed, so nobody else can be handed someone else's audit.
        """
        draft_id = self._check_id(draft_id)
        with self._session() as conn:
            mine = conn.execute(
                "SELECT payload FROM drafts WHERE id = ?", (draft_id,)
            ).fetchone()
            legacy = conn.execute(
                "SELECT payload, saved_at FROM drafts WHERE id = ?", (LEGACY_ID,)
            ).fetchone()

            if mine is not None:
                if legacy is not None and draft_id != LEGACY_ID:
                    conn.execute("DELETE FROM drafts WHERE id = ?", (LEGACY_ID,))
                return Workflow.from_json(mine["payload"])

            if legacy is None:
                return None

            workflow = Workflow.from_json(legacy["payload"])
            if draft_id != LEGACY_ID:
                conn.execute(
                    "INSERT INTO drafts (id, payload, saved_at) VALUES (?, ?, ?) "
                    "ON CONFLICT(id) DO UPDATE SET payload = excluded.payload, "
                    "saved_at = excluded.saved_at",
                    (draft_id, legacy["payload"], legacy["saved_at"]),
                )
                conn.execute("DELETE FROM drafts WHERE id = ?", (LEGACY_ID,))
        return workflow
