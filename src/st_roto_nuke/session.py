"""One open project (store + command bus) per project file for the whole Nuke session, used on the MAIN thread.
Keeping the bus alive keeps undo/redo history across panel actions and Track runs.

Opening a project also (T-071): marks it as open (`<project>.session.json`), detects an unclean previous session
(crash / power loss), checks integrity, restores the newest valid backup if the file is damaged (the damaged file
is kept), and starts automatic backups (every ST_ROTO_BACKUP_SECONDS, default 300 s, only after changes; a final
backup when Nuke exits). What happened is in `open_report(path)` and shown in the node status by the caller.
"""
from __future__ import annotations

import atexit
import os

from st_roto import persistence
from st_roto.commands import CommandBus
from st_roto.store import ProjectStore

_PROJECTS = {}
_EXTRAS = {}          # key -> {"marker", "autobackup", "report"}


def _key(path):
    return os.path.normcase(os.path.abspath(path))


def project(path: str):
    key = _key(path)
    if key not in _PROJECTS:
        report = {"previous_session": None, "recovery": None, "backup_on_open": None}
        marker = persistence.SessionMarker(path)
        prev = marker.acquire({"app": "nuke"})
        report["previous_session"] = prev
        if os.path.exists(path):
            rec = persistence.recover(path)                       # no-op when the file passes the check
            report["recovery"] = rec
            if prev and prev.get("state") == "crashed" and rec["action"] == "none":
                try:
                    report["backup_on_open"] = persistence.backup(path, reason="after_crash")
                except Exception as e:                            # report, never block opening
                    report["backup_on_open"] = "failed: %s" % e
        store = ProjectStore(path)
        _PROJECTS[key] = (store, CommandBus(store, author=os.environ.get("USERNAME") or "artist"))
        interval = float(os.environ.get("ST_ROTO_BACKUP_SECONDS", "300"))
        ab = persistence.AutoBackup(path, interval=interval).start() if interval > 0 else None
        _EXTRAS[key] = {"marker": marker, "autobackup": ab, "report": report}
    return _PROJECTS[key]


def open_report(path: str) -> dict:
    return _EXTRAS.get(_key(path), {}).get("report")


def report_text(path: str) -> str:
    """Artist-readable summary of anything unusual found when the project was opened ('' if nothing)."""
    r = open_report(path) or {}
    notes = []
    prev = r.get("previous_session")
    if prev:
        notes.append({"crashed": "the previous session ended unexpectedly (project checked)",
                      "open_elsewhere": "WARNING: this project is open in another Nuke (pid %s)" % prev.get("pid"),
                      "other_host": "WARNING: this project may be open on %s" % prev.get("host")}.get(prev.get("state"), ""))
    rec = r.get("recovery") or {}
    if rec.get("action") == "restored":
        notes.append("project file was damaged: restored backup %s (damaged file kept as %s)"
                     % (os.path.basename(rec["from"]), os.path.basename(rec["damaged"][0])))
    elif rec.get("action") == "failed":
        notes.append("project file is damaged and no valid backup was found (%s)" % rec["check"]["detail"])
    return "; ".join(n for n in notes if n)


def backup_now(path: str, reason: str = "manual") -> str:
    return persistence.backup(path, reason=reason)


def close(path: str):
    key = _key(path)
    ex = _EXTRAS.pop(key, None)
    pr = _PROJECTS.pop(key, None)
    if pr:
        pr[0].close()
    if ex:
        if ex["autobackup"]:
            ex["autobackup"].stop(final=True)
        ex["marker"].release()


def close_all():
    for key in list(_PROJECTS):
        close(key)


atexit.register(close_all)
