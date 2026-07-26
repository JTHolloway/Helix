"""Database connection, migration and backup.

Single responsibility: own the SQLite connection and keep the file safe.
No domain logic.

THE SAVE MODEL, stated plainly because it is the thing a decade of work
depends on:

  * Every edit is COMMITTED IMMEDIATELY. SQLite is a real database, not a
    document. There is no unsaved state, so there is no Save button and
    nothing to lose by closing the window or losing power.
  * A dated BACKUP is taken once a day, automatically, on first connection.
    Thirty are kept in ./backups/ beside the file.
  * MIGRATIONS run on open, so a file made today still opens in a version
    written years from now.
  * `helix archive` writes a portable zip whose JSON dump can be read
    without this program at all.
"""
from __future__ import annotations

import shutil
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

SCHEMA_VERSION = 2
_SCHEMA = Path(__file__).with_name("schema.sql")


def new_id() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------- migrations
# Each entry upgrades FROM its key TO the next version. Append, never edit:
# somebody's file is sitting at every version this program has ever had.
MIGRATIONS: dict[int, list[str]] = {
    1: [
        # v2 adds soft deletion, so "Remove from tree" can be undone.
        "ALTER TABLE person ADD COLUMN active INTEGER NOT NULL DEFAULT 1",
        "ALTER TABLE union_ ADD COLUMN active INTEGER NOT NULL DEFAULT 1",
        "CREATE INDEX IF NOT EXISTS ix_person_active ON person(active)",
    ],
}


def connect(path: str | Path, *, create: bool = True,
            backup_daily: bool = True,
            same_thread: bool = False) -> sqlite3.Connection:
    """Open a family file.

    `same_thread=False` because the local web server handles each request on
    its own thread while holding one connection. Helix is a single-user
    program, so concurrent writers are not the risk; the caller serialises
    access with a lock. Leaving the default would make every database-backed
    endpoint fail the moment it was called from a request thread.
    """
    path = Path(path)
    if not path.exists() and not create:
        raise FileNotFoundError(
            f"No family file at {path}. Run  helix init {path}  to make one."
        )
    existed = path.exists()
    con = sqlite3.connect(path, check_same_thread=same_thread)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    con.execute("PRAGMA synchronous = FULL")   # survive a power cut
    if existed and backup_daily:
        try:
            from .archive import daily_backup
            daily_backup(path)
        except Exception:
            pass                                # never block opening the file
    _migrate(con)
    return con


def _migrate(con: sqlite3.Connection) -> None:
    con.executescript(_SCHEMA.read_text())
    row = con.execute("SELECT v FROM settings WHERE k='schema_version'").fetchone()
    current = int(row["v"]) if row else 0
    if current == 0:
        con.execute("INSERT OR REPLACE INTO settings(k,v) VALUES('schema_version',?)",
                    (str(SCHEMA_VERSION),))
        con.commit()
        return
    while current < SCHEMA_VERSION:
        for stmt in MIGRATIONS.get(current, []):
            try:
                con.execute(stmt)
            except sqlite3.OperationalError as e:
                if "duplicate column" not in str(e).lower():
                    raise
        current += 1
        con.execute("UPDATE settings SET v=? WHERE k='schema_version'",
                    (str(current),))
    con.commit()


def checkpoint(con) -> None:
    """Fold the write-ahead log back into the main file. Do this before
    copying, emailing or backing up the file by hand, so the .helix is
    complete on its own."""
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    con.commit()


def backup(path: str | Path, keep: int = 30) -> Path:
    """Take a backup right now, whatever the date."""
    path = Path(path)
    d = path.parent / "backups"
    d.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = d / f"{path.stem}-{stamp}{path.suffix}"
    try:
        from .archive import _copy_consistent
        _copy_consistent(path, dest)
    except Exception:
        shutil.copy2(path, dest)
    olds = sorted(d.glob(f"{path.stem}-*{path.suffix}"))
    for old in olds[:-keep]:
        old.unlink()
    return dest


def get_setting(con, key: str, default=None):
    r = con.execute("SELECT v FROM settings WHERE k=?", (key,)).fetchone()
    return r["v"] if r else default


def set_setting(con, key: str, value) -> None:
    con.execute("INSERT INTO settings(k,v) VALUES(?,?) "
                "ON CONFLICT(k) DO UPDATE SET v=excluded.v", (key, str(value)))
    con.commit()
