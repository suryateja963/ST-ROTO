"""Per-project SQLite store (ADR-0005, D-027).

Essential project state lives here; regenerable data (AI features, cached masks) does not.
Design rules:
  * schema versions via PRAGMA user_version with forward-only migrations;
  * WAL journal + foreign keys; every mutation happens inside a transaction (see commands.CommandBus);
  * SQL kept to features available in old SQLite builds (no RETURNING, no UPSERT) for Nuke 13's Python 3.7.
"""
from __future__ import annotations

import datetime
import json
import os
import sqlite3

SCHEMA_VERSION = 5

_MIGRATIONS = {
    1: [
        """CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)""",
        """CREATE TABLE shots (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, source_path TEXT,
            width INTEGER, height INTEGER, first_frame INTEGER, last_frame INTEGER,
            created_utc TEXT NOT NULL)""",
        """CREATE TABLE objects (
            id TEXT PRIMARY KEY,
            shot_id TEXT NOT NULL REFERENCES shots(id) ON DELETE CASCADE,
            parent_id TEXT REFERENCES objects(id) ON DELETE CASCADE,
            name TEXT NOT NULL, origin TEXT NOT NULL, locked INTEGER NOT NULL DEFAULT 0,
            color TEXT, created_utc TEXT NOT NULL)""",
        """CREATE TABLE shapes (
            id TEXT PRIMARY KEY,
            object_id TEXT NOT NULL REFERENCES objects(id) ON DELETE CASCADE,
            name TEXT NOT NULL, point_count INTEGER NOT NULL, closed INTEGER NOT NULL DEFAULT 1,
            origin TEXT NOT NULL, locked INTEGER NOT NULL DEFAULT 0, generator TEXT,
            created_utc TEXT NOT NULL)""",
        """CREATE TABLE shape_keys (
            shape_id TEXT NOT NULL REFERENCES shapes(id) ON DELETE CASCADE,
            frame INTEGER NOT NULL, points TEXT NOT NULL, origin TEXT NOT NULL, generator TEXT,
            PRIMARY KEY (shape_id, frame))""",
        """CREATE TABLE operations (
            seq INTEGER PRIMARY KEY AUTOINCREMENT, ts_utc TEXT NOT NULL, author TEXT NOT NULL,
            actor TEXT NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL, inverse TEXT NOT NULL,
            undoes INTEGER REFERENCES operations(seq))""",
        """CREATE INDEX idx_objects_shot ON objects(shot_id)""",
        """CREATE INDEX idx_shapes_object ON shapes(object_id)""",
    ],
    2: [
        # Fingerprint of what ST-ROTO last wrote into a host shape (e.g. a Nuke Roto shape). A host shape whose
        # current fingerprint differs was edited by the artist in the host and must not be overwritten (REQ-042).
        """CREATE TABLE host_exports (
            host_tag TEXT PRIMARY KEY, shape_id TEXT NOT NULL, host TEXT NOT NULL,
            fingerprint TEXT NOT NULL, exported_utc TEXT NOT NULL)""",
    ],
    5: [
        # Shape-level feather (T-073), as Nuke Roto's shape attributes fx / fy (pixels) and ff (falloff exponent).
        """ALTER TABLE shapes ADD COLUMN feather_x REAL NOT NULL DEFAULT 0""",
        """ALTER TABLE shapes ADD COLUMN feather_y REAL NOT NULL DEFAULT 0""",
        """ALTER TABLE shapes ADD COLUMN feather_falloff REAL NOT NULL DEFAULT 1""",
    ],
    4: [
        # Fingerprint of the shot's source frames (T-075): proves a relinked path is the same footage.
        """ALTER TABLE shots ADD COLUMN source_fingerprint TEXT""",
    ],
    3: [
        # Per-frame AI diagnostics of the latest tracking run (also for frames where the AI found NO object).
        """CREATE TABLE key_reports (
            shape_id TEXT NOT NULL REFERENCES shapes(id) ON DELETE CASCADE,
            frame INTEGER NOT NULL, object_score REAL, iou_pred REAL,
            PRIMARY KEY (shape_id, frame))""",
    ],
}


def utc_now() -> str:
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


class ProjectStore:
    """Open (creating if needed) an ST-ROTO project database."""

    def __init__(self, path: str):
        self.path = path
        new = not os.path.exists(path)
        self.conn = sqlite3.connect(path, isolation_level=None)      # explicit BEGIN/COMMIT only
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self._migrate()
        if new:
            with self.transaction():
                self.conn.execute("INSERT INTO meta(key, value) VALUES ('created_utc', ?)", (utc_now(),))
                self.conn.execute("INSERT INTO meta(key, value) VALUES ('format', 'st-roto-project')", ())

    # -- schema ---------------------------------------------------------------------------------
    def schema_version(self) -> int:
        return int(self.conn.execute("PRAGMA user_version").fetchone()[0])

    def _migrate(self):
        current = self.schema_version()
        if current > SCHEMA_VERSION:
            raise RuntimeError("project %s has schema %d, newer than this ST-ROTO (%d)"
                               % (self.path, current, SCHEMA_VERSION))
        for v in range(current + 1, SCHEMA_VERSION + 1):
            with self.transaction():
                for sql in _MIGRATIONS[v]:
                    self.conn.execute(sql)
                self.conn.execute("PRAGMA user_version = %d" % v)

    # -- transactions -----------------------------------------------------------------------------
    def transaction(self):
        return _Tx(self.conn)

    # -- reads ------------------------------------------------------------------------------------
    def row(self, table: str, row_id: str):
        r = self.conn.execute("SELECT * FROM %s WHERE id = ?" % _table(table), (row_id,)).fetchone()
        return dict(r) if r else None

    def objects(self, shot_id: str):
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM objects WHERE shot_id = ? ORDER BY created_utc, id", (shot_id,))]

    def shapes(self, object_id: str):
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM shapes WHERE object_id = ? ORDER BY created_utc, id", (object_id,))]

    def key(self, shape_id: str, frame: int):
        r = self.conn.execute("SELECT * FROM shape_keys WHERE shape_id = ? AND frame = ?",
                              (shape_id, int(frame))).fetchone()
        if not r:
            return None
        d = dict(r)
        d["points"] = json.loads(d["points"])
        return d

    def keys(self, shape_id: str):
        out = []
        for r in self.conn.execute("SELECT * FROM shape_keys WHERE shape_id = ? ORDER BY frame", (shape_id,)):
            d = dict(r); d["points"] = json.loads(d["points"]); out.append(d)
        return out

    def reports(self, shape_id: str):
        return [dict(r) for r in self.conn.execute(
            "SELECT frame, object_score, iou_pred FROM key_reports WHERE shape_id = ? ORDER BY frame", (shape_id,))]

    def operations(self):
        return [dict(r) for r in self.conn.execute("SELECT * FROM operations ORDER BY seq")]

    def close(self):
        self.conn.close()


class _Tx:
    """Re-entrant-safe transaction context: BEGIN IMMEDIATE ... COMMIT, ROLLBACK on any exception."""

    def __init__(self, conn):
        self.conn = conn
        self.outer = not conn.in_transaction

    def __enter__(self):
        if self.outer:
            self.conn.execute("BEGIN IMMEDIATE")
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        if self.outer:
            self.conn.execute("ROLLBACK" if exc_type else "COMMIT")
        return False


def _table(name: str) -> str:
    if name not in ("shots", "objects", "shapes"):
        raise ValueError("unknown table %r" % name)
    return name
