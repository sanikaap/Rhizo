import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, fields
from pathlib import Path
from secrets import token_hex
from typing import Any, Literal

from rhizo.config import settings
from rhizo.core.timeutil import now_epoch

Status = Literal["queued", "cloning", "detecting", "ingesting", "ready", "failed"]
IN_PROGRESS: tuple[Status, ...] = ("queued", "cloning", "detecting", "ingesting")
RUNNING: tuple[Status, ...] = ("cloning", "detecting", "ingesting")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS repos (
    id             TEXT PRIMARY KEY,
    user_id        TEXT NOT NULL,
    owner          TEXT NOT NULL,
    name           TEXT NOT NULL,
    status         TEXT NOT NULL,
    progress       INTEGER NOT NULL DEFAULT 0,
    message        TEXT,
    error          TEXT,
    last_synced_at INTEGER,
    created_at     INTEGER NOT NULL,
    is_demo        INTEGER NOT NULL DEFAULT 0,
    UNIQUE (user_id, owner, name)
);
CREATE INDEX IF NOT EXISTS repos_user ON repos(user_id);
CREATE TABLE IF NOT EXISTS accounts (
    user_id        TEXT PRIMARY KEY,
    demo_dismissed INTEGER NOT NULL DEFAULT 0,
    created_at     INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS evaluations (
    repo_id    TEXT PRIMARY KEY,
    result     TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
"""


@dataclass(frozen=True)
class Repo:
    id: str
    user_id: str
    owner: str
    name: str
    status: Status
    progress: int
    message: str | None
    error: str | None
    last_synced_at: int | None
    created_at: int
    is_demo: bool

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"


_COLUMNS = [f.name for f in fields(Repo)]
_UPDATABLE = {"status", "progress", "message", "error", "last_synced_at"}
_lock = threading.Lock()


@contextmanager
def _db() -> Iterator[sqlite3.Connection]:
    path = Path(settings.registry_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        conn = sqlite3.connect(path, timeout=5)
        try:
            conn.executescript(_SCHEMA)
            _migrate(conn)
            conn.row_factory = sqlite3.Row
            yield conn
            conn.commit()
        finally:
            conn.close()


def _migrate(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(repos)")}
    if "is_demo" not in columns:
        conn.execute("ALTER TABLE repos ADD COLUMN is_demo INTEGER NOT NULL DEFAULT 0")


def _repo(row: sqlite3.Row | None) -> Repo | None:
    if not row:
        return None
    values: dict[str, Any] = {c: row[c] for c in _COLUMNS}
    values["is_demo"] = bool(values["is_demo"])
    return Repo(**values)


def create(user_id: str, owner: str, name: str, is_demo: bool = False) -> Repo:
    repo = Repo(
        id=token_hex(6),
        user_id=user_id,
        owner=owner,
        name=name,
        status="queued",
        progress=0,
        message="Waiting to start",
        error=None,
        last_synced_at=None,
        created_at=now_epoch(),
        is_demo=is_demo,
    )
    with _db() as conn:
        conn.execute(
            f"INSERT INTO repos ({', '.join(_COLUMNS)}) VALUES ({', '.join('?' * len(_COLUMNS))})",
            [getattr(repo, c) for c in _COLUMNS],
        )
    return repo


def list_for(user_id: str) -> list[Repo]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM repos WHERE user_id = ? ORDER BY created_at DESC", (user_id,)
        ).fetchall()
    return [r for r in map(_repo, rows) if r]


def get(user_id: str, repo_id: str) -> Repo | None:
    with _db() as conn:
        row = conn.execute("SELECT * FROM repos WHERE id = ? AND user_id = ?", (repo_id, user_id)).fetchone()
    return _repo(row)


def get_any(repo_id: str) -> Repo | None:
    with _db() as conn:
        return _repo(conn.execute("SELECT * FROM repos WHERE id = ?", (repo_id,)).fetchone())


def update(repo_id: str, **changes: Any) -> None:
    bad = set(changes) - _UPDATABLE
    if bad:
        raise ValueError(f"not updatable: {sorted(bad)}")
    assignments = ", ".join(f"{k} = ?" for k in changes)
    with _db() as conn:
        conn.execute(f"UPDATE repos SET {assignments} WHERE id = ?", [*changes.values(), repo_id])


def claim_for_sync(user_id: str, repo_id: str) -> bool:
    placeholders = ", ".join("?" * len(IN_PROGRESS))
    with _db() as conn:
        cur = conn.execute(
            f"UPDATE repos SET status = 'queued', progress = 0, message = 'Waiting to start', error = NULL "
            f"WHERE id = ? AND user_id = ? AND status NOT IN ({placeholders})",
            [repo_id, user_id, *IN_PROGRESS],
        )
        return cur.rowcount == 1


def delete(user_id: str, repo_id: str) -> bool:
    with _db() as conn:
        owned = conn.execute(
            "SELECT 1 FROM repos WHERE id = ? AND user_id = ?", (repo_id, user_id)
        ).fetchone()
        if not owned:
            return False
        conn.execute("DELETE FROM evaluations WHERE repo_id = ?", (repo_id,))
        conn.execute("DELETE FROM repos WHERE id = ? AND user_id = ?", (repo_id, user_id))
        return True


def ensure_account(user_id: str) -> bool:
    with _db() as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO accounts (user_id, created_at) VALUES (?, ?)", (user_id, now_epoch())
        )
        return cur.rowcount == 1


def demo_dismissed(user_id: str) -> bool:
    with _db() as conn:
        row = conn.execute("SELECT demo_dismissed FROM accounts WHERE user_id = ?", (user_id,)).fetchone()
    return bool(row and row["demo_dismissed"])


def set_demo_dismissed(user_id: str, dismissed: bool) -> None:
    ensure_account(user_id)
    with _db() as conn:
        conn.execute("UPDATE accounts SET demo_dismissed = ? WHERE user_id = ?", (int(dismissed), user_id))


def demo_for(user_id: str) -> Repo | None:
    with _db() as conn:
        return _repo(
            conn.execute("SELECT * FROM repos WHERE user_id = ? AND is_demo = 1", (user_id,)).fetchone()
        )


def save_evaluation(repo_id: str, result_json: str) -> None:
    with _db() as conn:
        conn.execute(
            "INSERT INTO evaluations (repo_id, result, created_at) VALUES (?, ?, ?) "
            "ON CONFLICT(repo_id) DO UPDATE SET result = excluded.result, created_at = excluded.created_at",
            (repo_id, result_json, now_epoch()),
        )


def evaluation(user_id: str, repo_id: str) -> str | None:
    with _db() as conn:
        row = conn.execute(
            "SELECT e.result FROM evaluations e JOIN repos r ON r.id = e.repo_id "
            "WHERE r.id = ? AND r.user_id = ?",
            (repo_id, user_id),
        ).fetchone()
    return row["result"] if row else None


def fail_interrupted() -> int:
    placeholders = ", ".join("?" * len(IN_PROGRESS))
    with _db() as conn:
        cur = conn.execute(
            f"UPDATE repos SET status = 'failed', error = 'Interrupted by a server restart. Sync again.' "
            f"WHERE status IN ({placeholders})",
            IN_PROGRESS,
        )
        return cur.rowcount
