"""The ST_Roto node (single-node core under the Non-commercial 10-node cap, D-012) — vertical slice v0.

Structure: Group "ST_Roto" with  Input -> Roto(STROTO_shapes, alpha) -> Output, plus a disabled Write
(STROTO_pixels) used to pull pixels into numpy. 5 nodes per shot incl. the group.
Knobs (tab ST-ROTO): project file, object name, click position (XY, Nuke coordinates) and frame, model, device,
Track / Cancel buttons, status. Tracking runs on a worker thread; Nuke calls are marshalled to the main thread.
"""
from __future__ import annotations

import os

import nuke
import nuke.rotopaint  # noqa: F401  (ensures the rotopaint module is initialised)

from st_roto import jobs
from st_roto.commands import CommandBus
from st_roto.store import ProjectStore
from . import pixels
from .roto_export import export_shape
from .track import apply_result, track_object

MODELS = ["sam2.1-hiera-tiny", "sam2.1-hiera-large"]
DEVICES = ["auto", "cpu"]
_JOBS = {}            # group full name -> running Job
_INNER = {}           # group full name -> {"write": Node, "roto": Node}: avoids re-fetching nodes (10-node budget)


class NodeBudgetError(RuntimeError):
    """Nuke Non-commercial / Indie returned None because the 10-Python-Node-object limit was reached (ADR-0003)."""


def _inner(group, key, name):
    cached = _INNER.get(group.fullName(), {}).get(key)
    if cached is not None:
        return cached
    with group:
        n = nuke.toNode(name)
    if n is None:
        raise NodeBudgetError("Nuke returned no node for %s.%s. In Non-commercial/Indie mode Python can access only "
                              "10 nodes per session; save the script, reopen it and press Track again."
                              % (group.name(), name))
    _INNER.setdefault(group.fullName(), {})[key] = n
    return n


def create(source=None, project_path: str = ""):
    group = nuke.nodes.Group(name="ST_Roto1")
    if source is not None:
        group.setInput(0, source)
    tab = nuke.Tab_Knob("stroto_tab", "ST-ROTO")
    group.addKnob(tab)
    k = nuke.File_Knob("stroto_project", "project file"); group.addKnob(k); k.setValue(project_path)
    group.addKnob(nuke.String_Knob("stroto_object", "object name", "object1"))
    group.addKnob(nuke.XY_Knob("stroto_click", "click (x, y)"))
    group.addKnob(nuke.Int_Knob("stroto_click_frame", "click frame"))
    group.addKnob(nuke.Enumeration_Knob("stroto_model", "model", MODELS))
    group.addKnob(nuke.Enumeration_Knob("stroto_device", "device", DEVICES))
    b = nuke.PyScript_Knob("stroto_track", "Track", "import st_roto_nuke.node as n; n.on_track(nuke.thisNode())")
    group.addKnob(b)
    c = nuke.PyScript_Knob("stroto_cancel", "Cancel", "import st_roto_nuke.node as n; n.on_cancel(nuke.thisNode())")
    group.addKnob(c)
    st = nuke.Text_Knob("stroto_status", "status", "idle")
    group.addKnob(st)
    with group:
        inp = nuke.nodes.Input(name="Input1")
        roto = nuke.nodes.Roto(name="STROTO_shapes", output="alpha")
        roto.setInput(0, inp)
        out = nuke.nodes.Output(name="Output1")
        out.setInput(0, roto)
        w = nuke.nodes.Write(name="STROTO_pixels")
        w.setInput(0, inp)
        pixels.configure_write(w, pixels.temp_pixel_path(group.name()))
        w["disable"].setValue(True)
    _INNER[group.fullName()] = {"write": w, "roto": roto}
    return group


def _status(group, text):
    def _set():
        group["stroto_status"].setValue(text)
    if _is_main_thread():
        _set()
    else:
        nuke.executeInMainThread(_set)


def _is_main_thread():
    import threading
    return threading.current_thread() is threading.main_thread()


def on_cancel(group):
    job = _JOBS.get(group.fullName())
    if job:
        job.cancel()


def on_track(group, background: bool = True):
    """Button callback. Collects parameters on the main thread, runs tracking on a worker thread, applies the
    result (project store + native Roto shape) back on the main thread. Returns the Job."""
    if group.fullName() in _JOBS and _JOBS[group.fullName()].status == jobs.RUNNING:
        _status(group, "already running")
        return _JOBS[group.fullName()]
    src = group.input(0)
    if src is None:
        _status(group, "error: connect a source to the ST_Roto input"); return None
    project = group["stroto_project"].value()
    if not project:
        _status(group, "error: set a project file"); return None
    first, last = int(src.firstFrame()), int(src.lastFrame())
    click_frame = int(group["stroto_click_frame"].value())
    width, height = int(src.width()), int(src.height())
    cx, cy_nuke = group["stroto_click"].value()
    click_xy = (float(cx), float(height) - float(cy_nuke))           # Nuke (y up) -> canonical (y down)
    frames = list(range(click_frame, last + 1))
    if click_frame < first or click_frame > last:
        _status(group, "error: click frame %d outside source range %d-%d" % (click_frame, first, last)); return None
    model = group["stroto_model"].value()
    device = group["stroto_device"].value()
    obj_name = group["stroto_object"].value() or "object"
    try:
        write = _inner(group, "write", "STROTO_pixels")
        roto = _inner(group, "roto", "STROTO_shapes")
    except NodeBudgetError as e:
        _status(group, "error: " + str(e)); return None
    path = pixels.temp_pixel_path(group.name())

    def get_rgb(frame):
        if background:
            return nuke.executeInMainThreadWithResult(pixels.render_frame, (write, frame, path))
        return pixels.render_frame(write, frame, path)

    def work(job):
        return track_object(get_rgb, frames, click_frame, click_xy, model=model, device=device, job=job)

    def apply(job):
        # Runs on the main thread via executeInMainThread: exceptions there are NOT propagated anywhere,
        # so every failure must be caught and shown on the node (found by tests/nuke/gui_track_slice.py).
        try:
            _apply(job)
        except Exception:
            import traceback
            job.apply_error = traceback.format_exc()
            job.applied = "failed applying result: " + job.apply_error.strip().splitlines()[-1]
            group["stroto_status"].setValue(job.applied)

    def _apply(job):
        result = job.result
        store = ProjectStore(project)
        try:
            bus = CommandBus(store, author=os.environ.get("USERNAME", "artist"))
            shot_id = _ensure_shot(store, bus, src, width, height, first, last)
            oid, sid = apply_result(bus, shot_id, obj_name, result)
            export_shape(store, sid, roto["curves"], height)
        finally:
            store.close()
        msg = "done: %d keys, %d frames without object, device %s" % (
            len(result["keys"]), len(result["absent_frames"]), result["device"])
        if result["device_fallback"]:
            msg += " (FALLBACK: %s)" % result["device_reason"]
        group["stroto_status"].setValue(msg)
        job.applied = msg

    def finished(job):
        if job.status == jobs.DONE:
            if background:
                nuke.executeInMainThread(apply, (job,))
            else:
                apply(job)
        elif job.status == jobs.FAILED:
            _status(group, "failed: " + job.error.strip().splitlines()[-1])
        else:
            _status(group, "cancelled")

    job = jobs.Job(work, name="track", on_progress=lambda j: _status(group, "tracking %d%%: %s" % (100 * j.progress, j.message)),
                   on_finish=finished)
    job.applied = None
    job.apply_error = None
    _JOBS[group.fullName()] = job
    return job.start(background=background)


def _ensure_shot(store, bus, src, width, height, first, last):
    """One shot per project in v0, keyed by the source node name."""
    name = src.name()
    for r in store.conn.execute("SELECT id FROM shots WHERE name = ?", (name,)):
        return r["id"]
    from st_roto import model as m
    sid = m.new_id()
    bus.execute({"op": "create_shot", "row": {"id": sid, "name": name, "width": width, "height": height,
                                              "first_frame": first, "last_frame": last}})
    return sid
