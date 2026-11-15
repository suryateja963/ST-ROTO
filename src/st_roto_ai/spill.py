"""Bounded-RAM store for per-frame tracker state (T-065, R-42).

Behaves like a dict of {frame: {name: ndarray}}. At most `max_in_ram` entries stay in memory (least recently used
are written to `directory` as .npz and reloaded on demand), so tracker results are IDENTICAL to keeping everything
in RAM (upstream behaviour) while memory stays bounded for long shots.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from collections import OrderedDict

import numpy as np


class SpillDict:
    def __init__(self, max_in_ram: int = 24, directory: str | None = None):
        self.max_in_ram = max(1, int(max_in_ram))
        self._own_dir = directory is None
        self.dir = directory or tempfile.mkdtemp(prefix="st_roto_track_")
        os.makedirs(self.dir, exist_ok=True)
        self._ram = OrderedDict()
        self._disk = set()
        self.spills = self.loads = 0

    def _path(self, key):
        return os.path.join(self.dir, "f%d.npz" % key)

    def __setitem__(self, key, value):
        self._ram[key] = value
        self._ram.move_to_end(key)
        self._disk.discard(key)
        self._evict()

    def _evict(self):
        while len(self._ram) > self.max_in_ram:
            k, v = self._ram.popitem(last=False)
            np.savez(self._path(k), **v)
            self._disk.add(k)
            self.spills += 1

    def get(self, key, default=None):
        if key in self._ram:
            self._ram.move_to_end(key)
            return self._ram[key]
        if key in self._disk:
            with np.load(self._path(key)) as z:
                v = {n: z[n] for n in z.files}
            self.loads += 1
            self._ram[key] = v
            self._disk.discard(key)
            self._evict()
            return v
        return default

    def __contains__(self, key):
        return key in self._ram or key in self._disk

    def __len__(self):
        return len(self._ram) + len(self._disk)

    @property
    def in_ram(self):
        return len(self._ram)

    def close(self):
        if self._own_dir:
            shutil.rmtree(self.dir, ignore_errors=True)

    # -- checkpoints (T-048) ------------------------------------------------------------------
    def export_to(self, directory: str) -> list:
        """Write every entry to `directory` as f<key>.npz, skipping files already there (entries never change
        once written: tracked-frame state is immutable). Returns the keys."""
        os.makedirs(directory, exist_ok=True)
        keys = sorted(set(self._ram) | self._disk)
        for k in keys:
            dst = os.path.join(directory, "f%d.npz" % k)
            if os.path.exists(dst):
                continue
            tmp = dst + ".part.npz"
            if k in self._ram:
                np.savez(tmp, **self._ram[k])
            else:
                shutil.copyfile(self._path(k), tmp)
            os.replace(tmp, dst)
        return keys

    def import_from(self, directory: str, keys) -> None:
        """Adopt entries exported by `export_to` (copied into this store's own folder, loaded on demand)."""
        for k in keys:
            shutil.copyfile(os.path.join(directory, "f%d.npz" % k), self._path(k))
            self._ram.pop(k, None)
            self._disk.add(k)
