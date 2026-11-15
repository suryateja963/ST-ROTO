"""One open project (store + command bus) per project file for the whole Nuke session, used on the MAIN thread.
Keeping the bus alive keeps undo/redo history across panel actions and Track runs."""
from __future__ import annotations

import os

from st_roto.commands import CommandBus
from st_roto.store import ProjectStore

_PROJECTS = {}


def project(path: str):
    key = os.path.normcase(os.path.abspath(path))
    if key not in _PROJECTS:
        store = ProjectStore(path)
        _PROJECTS[key] = (store, CommandBus(store, author=os.environ.get("USERNAME") or "artist"))
    return _PROJECTS[key]


def close_all():
    for store, _ in _PROJECTS.values():
        store.close()
    _PROJECTS.clear()
