"""Cancellable background jobs (ADR-0009). Pure Python: no Nuke, no Qt.

A job function receives the Job and calls `job.check()` regularly (raises Cancelled) and `job.report(p, msg)`.
Measured in Nuke 17.1's GUI: GPU work on a worker thread keeps the UI at full rate; cooperative cancellation
took ~39 ms (research/probes/2026-11-15_gui_threading).
"""
from __future__ import annotations

import threading
import time
import traceback


class Cancelled(Exception):
    pass


PENDING, RUNNING, DONE, FAILED, CANCELLED = "pending", "running", "done", "failed", "cancelled"


class Job:
    def __init__(self, fn, name: str = "job", on_progress=None, on_finish=None):
        self.fn, self.name = fn, name
        self.on_progress, self.on_finish = on_progress, on_finish
        self.status = PENDING
        self.progress, self.message = 0.0, ""
        self.result = None
        self.error = None
        self._cancel = threading.Event()
        self._thread = None
        self.started = self.finished = None

    # -- called by the job function ---------------------------------------------------------------
    def check(self):
        if self._cancel.is_set():
            raise Cancelled(self.name)

    def report(self, progress: float, message: str = ""):
        self.progress, self.message = float(progress), message
        if self.on_progress:
            self.on_progress(self)

    # -- control ----------------------------------------------------------------------------------
    def cancel(self):
        self._cancel.set()

    def start(self, background: bool = True):
        if background:
            self._thread = threading.Thread(target=self._run, name="st_roto:" + self.name, daemon=True)
            self._thread.start()
        else:
            self._run()
        return self

    def wait(self, timeout=None) -> bool:
        if self._thread is not None:
            self._thread.join(timeout)
            return not self._thread.is_alive()
        return self.status in (DONE, FAILED, CANCELLED)

    def _run(self):
        self.status, self.started = RUNNING, time.time()
        try:
            self.result = self.fn(self)
            self.status = DONE
        except Cancelled:
            self.status = CANCELLED
        except Exception:                         # surfaced to the UI, never swallowed silently
            self.status, self.error = FAILED, traceback.format_exc()
        self.finished = time.time()
        if self.on_finish:
            self.on_finish(self)
