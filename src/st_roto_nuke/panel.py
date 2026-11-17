"""ST-ROTO object panel (dockable). Lists the objects of the selected ST_Roto node's shot and edits them through the
command bus (artist actor): rename, lock/unlock, delete, undo, redo. After each edit the Roto node is re-synchronised;
shapes edited directly in the Roto node are never overwritten (reported instead).

Register as a dockable pane (done by nuke_plugin/menu.py):
    nukescripts.panels.registerWidgetAsPanel("st_roto_nuke.panel.ObjectPanel", "ST-ROTO Objects", "st_roto.objects")
"""
from __future__ import annotations

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:                       # Nuke 13-15 ship PySide2
    from PySide2 import QtCore, QtGui, QtWidgets

import nuke

from st_roto import views
from . import collab
from . import node as stnode
from . import session

COLUMNS = ["name", "role", "origin", "locked", "held by", "keys", "frames", "review"]


TIMELINE_COLOURS = {"artist": (255, 150, 40), "ai": (150, 150, 150), "lost": (230, 40, 40), "check": (235, 200, 40),
                    "locked": (60, 110, 220), "current": (255, 255, 255)}


class TimelineWidget(QtWidgets.QWidget):
    """One row per object across the shot (T-102, REQ-120): artist keys (orange), AI keys (grey), locked frames
    (blue band), review flags lost (red) / check (yellow) under the keys, current frame (white line). Click: jump
    to that frame and select the object (on_pick(frame, row))."""
    ROW_H, LABEL_W = 18, 90

    def __init__(self, parent=None, on_pick=None):
        super().__init__(parent)
        self.rows, self.first, self.last, self.current, self.on_pick = [], 0, 0, None, on_pick
        self.setMinimumHeight(self.ROW_H * 2)

    def set_data(self, rows, first, last, current=None):
        self.rows, self.first, self.last, self.current = rows, int(first), int(max(last, first)), current
        self.setMinimumHeight(self.ROW_H * max(2, len(rows) + 1))
        self.update()

    def x_of(self, frame):
        span = max(1, self.last - self.first + 1)
        return self.LABEL_W + (frame - self.first + 0.5) * (self.width() - self.LABEL_W) / float(span)

    def frame_at(self, x):
        span = max(1, self.last - self.first + 1)
        f = self.first + int((x - self.LABEL_W) * span / float(max(1, self.width() - self.LABEL_W)))
        return min(self.last, max(self.first, f))

    def paintEvent(self, event):                              # noqa: N802 (Qt API)
        p = QtGui.QPainter(self)
        p.fillRect(self.rect(), QtGui.QColor(40, 40, 40))
        col = lambda k: QtGui.QColor(*TIMELINE_COLOURS[k])    # noqa: E731
        for i, r in enumerate(self.rows):
            y = i * self.ROW_H
            p.setPen(QtGui.QColor(220, 220, 220))
            p.drawText(4, y + self.ROW_H - 5, r["name"][:12])
            for f in r["locked"]:
                p.fillRect(QtCore.QRectF(self.x_of(f) - 2, y + 2, 4, self.ROW_H - 4), col("locked"))
            for f, kind in r["keys"].items():
                x = self.x_of(f)
                p.fillRect(QtCore.QRectF(x - 1, y + 4, 2, self.ROW_H - 10), col(kind))
            for f, level in r["flags"].items():
                p.fillRect(QtCore.QRectF(self.x_of(f) - 2, y + self.ROW_H - 5, 4, 3), col(level))
        if self.current is not None and self.first <= self.current <= self.last:
            p.setPen(col("current"))
            x = int(self.x_of(self.current))
            p.drawLine(x, 0, x, self.height())
        p.end()

    def mousePressEvent(self, event):                         # noqa: N802 (Qt API)
        pos = event.position() if hasattr(event, "position") else event.pos()
        row = int(pos.y() // self.ROW_H)
        if pos.x() < self.LABEL_W or row >= len(self.rows):
            return
        frame = self.frame_at(pos.x())
        if self.on_pick:
            self.on_pick(frame, row)


class ObjectPanel(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.group = None
        self.rows = []
        lay = QtWidgets.QVBoxLayout(self)
        top = QtWidgets.QHBoxLayout()
        self.use_btn = QtWidgets.QPushButton("Use selected ST_Roto node")
        self.use_btn.clicked.connect(self.use_selected)
        top.addWidget(self.use_btn)
        self.refresh_btn = QtWidgets.QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh)
        top.addWidget(self.refresh_btn)
        lay.addLayout(top)
        self.table = QtWidgets.QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        lay.addWidget(self.table)
        self.timeline = TimelineWidget(self, on_pick=self.pick)
        self.timeline.setToolTip("Keys: orange = artist, grey = AI; blue = locked; under the keys: red = REVIEW lost, "
                                 "yellow = check. Click to go to that frame and select the object.")
        lay.addWidget(self.timeline)
        btns = QtWidgets.QHBoxLayout()
        for label, fn in (("Rename", self.rename), ("Lock / Unlock", self.toggle_lock), ("Role...", self.set_object_role),
                          ("Merge into...", self.merge_into), ("Delete", self.delete),
                          ("Undo", self.undo), ("Redo", self.redo)):
            b = QtWidgets.QPushButton(label); b.clicked.connect(fn); btns.addWidget(b)
        lay.addLayout(btns)
        # collaboration (T-094): leases, roles, signing key, presence
        cb = QtWidgets.QHBoxLayout()
        for label, fn, tip in (
                ("Take", self.take, "Lease the selected object: only you can change it until you release it."),
                ("Release", self.release, "Give your lease on the selected object back."),
                ("Override", self.override, "Supervisors only: take the lease of someone idle or offline for 15 "
                                            "minutes (D-035/D-036); the evidence is recorded."),
                ("Set up signing key", self.setup_key, "Create your private key (in your user folder, never in the "
                                                       "project) and register it: your changes are then signed."),
                ("Set role...", self.set_role, "The project's first role must be you as admin; then admins assign "
                                               "artist / supervisor / admin.")):
            b = QtWidgets.QPushButton(label); b.setToolTip(tip); b.clicked.connect(fn); cb.addWidget(b)
        lay.addLayout(cb)
        self.collab_info = QtWidgets.QLabel("")
        self.collab_info.setWordWrap(True)
        lay.addWidget(self.collab_info)
        self.info = QtWidgets.QLabel("select an ST_Roto node and press 'Use selected ST_Roto node'")
        self.info.setWordWrap(True)
        lay.addWidget(self.info)
        try:
            from PySide6 import QtCore
        except ImportError:
            from PySide2 import QtCore
        self.timer = QtCore.QTimer(self)                      # presence heartbeat while the panel is open
        self.timer.setInterval(collab.ACTIVITY_SECONDS * 1000)
        self.timer.timeout.connect(self._heartbeat)
        self.timer.start()

    # -- model ------------------------------------------------------------------------------------
    def set_group(self, group):
        self.group = group
        self.refresh()

    def use_selected(self):
        try:
            n = nuke.selectedNode()
        except ValueError:
            self.info.setText("no node selected"); return
        if "stroto_project" not in n.knobs():
            self.info.setText("%s is not an ST_Roto node" % n.name()); return
        self.set_group(n)

    def _project(self):
        if self.group is None:
            raise ValueError("no ST_Roto node chosen")
        path = self.group["stroto_project"].value()
        if not path:
            raise ValueError("the ST_Roto node has no project file")
        return session.project(path)

    def refresh(self):
        try:
            store, bus = self._project()
            shot = stnode.shot_id_for(self.group)
        except Exception as e:
            self.info.setText(str(e)); return
        from st_roto import quality
        path = self.group["stroto_project"].value()
        me_ = bus.author
        self.rows = views.object_rows(store, shot) if shot else []
        self.table.setRowCount(len(self.rows))
        for i, r in enumerate(self.rows):
            frames = "" if r["first"] is None else "%d-%d" % (r["first"], r["last"])
            flags = views.review_for_object(store, r["id"])
            r["review"] = flags
            review = quality.summary(flags)
            held = collab.lease_text(store.conn, r["id"], me_)
            role = (store.row("objects", r["id"]) or {}).get("role") or "add"
            for j, v in enumerate([r["name"], "" if role == "add" else role, r["origin"], "yes" if r["locked"] else "",
                                   held, str(r["keys"]), frames, review]):
                item = QtWidgets.QTableWidgetItem(v)
                if j == 7 and flags:
                    item.setToolTip("\n".join("frame %d [%s]: %s" % fr for fr in flags))
                self.table.setItem(i, j, item)
        self.info.setText("%d objects · undo %s · redo %s" % (len(self.rows), "yes" if bus.can_undo() else "no",
                                                            "yes" if bus.can_redo() else "no"))
        try:
            shot_row = store.row("shots", shot) if shot else None
            first = shot_row["first_frame"] if shot_row and shot_row["first_frame"] is not None else 0
            last = shot_row["last_frame"] if shot_row and shot_row["last_frame"] is not None else first
            by_id = {t["id"]: t for t in views.timeline(store, shot)} if shot else {}
            self.timeline.set_data([by_id[r["id"]] for r in self.rows if r["id"] in by_id], first, last,
                                   int(nuke.frame()))
        except Exception as e:                                # noqa: BLE001
            self.info.setText(self.info.text() + " · timeline: %s" % e)
        try:
            self.collab_info.setText(collab.status_line(path))
        except Exception as e:                                # noqa: BLE001
            self.collab_info.setText("collaboration: %s" % e)

    def pick(self, frame, row):
        """Timeline click: go to `frame` and select the object of `row`."""
        nuke.frame(frame)
        if 0 <= row < len(self.rows):
            self.table.selectRow(row)
        self.timeline.current = frame
        self.timeline.update()
        return frame

    def _selected(self):
        idx = self.table.currentRow()
        if idx < 0 or idx >= len(self.rows):
            raise ValueError("select an object row first")
        return self.rows[idx]

    # -- actions (all through the command bus, actor = artist) -------------------------------------
    def _do(self, fn):
        try:
            store, bus = self._project()
            fn(bus)
            rep = stnode.resync(self.group)
            self.refresh()
            if rep["conflicts"]:
                self.info.setText(self.info.text() + " · NOT updated (edited in Roto): " + ", ".join(rep["conflicts"]))
            return rep
        except Exception as e:
            self.info.setText("error: %s" % e)
            return None

    def rename(self, new_name=None):
        r = self._selected()
        if new_name is None:
            new_name, ok = QtWidgets.QInputDialog.getText(self, "Rename object", "name", text=r["name"])
            if not ok:
                return None
        def op(bus):
            store = bus.store
            bus.execute({"op": "batch", "ops": views.rename_ops(store, r["id"], new_name)})  # one undo step
        return self._do(op)

    def toggle_lock(self):
        r = self._selected()
        return self._do(lambda bus: bus.execute({"op": "update_object", "id": r["id"],
                                                 "fields": {"locked": 0 if r["locked"] else 1}}))

    def set_object_role(self, role=None):
        r = self._selected()
        if role is None:
            role, ok = QtWidgets.QInputDialog.getItem(self, "Object role", "role of %s" % r["name"],
                                                      ["add", "holdout", "garbage"], 0, False)
            if not ok:
                return None
        if role != "add":
            stnode._ensure_clamp(self.group)
        return self._do(lambda bus: bus.execute({"op": "update_object", "id": r["id"], "fields": {"role": role}}))

    def merge_into(self, target_name=None):
        """Merge the selected object into another one (its shapes move; one undo step)."""
        r = self._selected()
        others = [x["name"] for x in self.rows if x["id"] != r["id"]]
        if target_name is None:
            target_name, ok = QtWidgets.QInputDialog.getItem(self, "Merge", "merge %s into" % r["name"], others, 0, False)
            if not ok:
                return None
        tgt = [x for x in self.rows if x["name"] == target_name]
        if not tgt:
            self.info.setText("error: no object named %r" % target_name); return None
        return self._do(lambda bus: bus.execute({"op": "batch", "ops": views.merge_ops(bus.store, r["id"], tgt[0]["id"])}))

    def delete(self):
        r = self._selected()
        return self._do(lambda bus: bus.execute({"op": "delete_subtree", "object_id": r["id"]}))

    def undo(self):
        return self._do(lambda bus: bus.undo())

    # -- collaboration (T-094) -------------------------------------------------------------------------
    def _path(self):
        if self.group is None:
            raise ValueError("no ST_Roto node chosen")
        return self.group["stroto_project"].value()

    def _collab(self, fn, done):
        try:
            fn(self._path())
            self.refresh()
            self.info.setText(done)
            return True
        except Exception as e:                                # rule refusals come back as readable messages
            self.info.setText("error: %s" % e)
            return False

    def take(self):
        r = self._selected()
        return self._collab(lambda p: collab.take(p, r["id"]), "you hold %s" % r["name"])

    def release(self):
        r = self._selected()
        return self._collab(lambda p: collab.release(p, r["id"]), "released %s" % r["name"])

    def override(self):
        r = self._selected()
        return self._collab(lambda p: collab.override(p, r["id"]), "took over %s (supervisor override)" % r["name"])

    def setup_key(self):
        out = {}

        def fn(p):
            out["state"], out["created"] = collab.setup_key(p)
        ok = self._collab(fn, "")
        if ok:
            self.info.setText("signing key %s%s" % ("created and " if out["created"] else "", out["state"]))
        return ok

    def set_role(self, user=None, role_name=None):
        if user is None:
            user, ok = QtWidgets.QInputDialog.getText(self, "Set role", "user name", text=collab.me(self._path()))
            if not ok:
                return None
            role_name, ok = QtWidgets.QInputDialog.getItem(self, "Set role", "role", list(collab.leases.ROLES), 0,
                                                           False)
            if not ok:
                return None
        return self._collab(lambda p: collab.set_role(p, user, role_name), "%s is now %s" % (user, role_name))

    def _heartbeat(self):
        try:
            if self.group is not None and self.isVisible():
                collab.heartbeat(self._path(), frame=int(nuke.frame()), activity="object panel")
        except Exception:                                     # noqa: BLE001 - presence must never interrupt work
            pass

    def redo(self):
        return self._do(lambda bus: bus.redo())
