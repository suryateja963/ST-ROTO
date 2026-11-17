"""ST-ROTO object panel (dockable). Lists the objects of the selected ST_Roto node's shot and edits them through the
command bus (artist actor): rename, lock/unlock, delete, undo, redo. After each edit the Roto node is re-synchronised;
shapes edited directly in the Roto node are never overwritten (reported instead).

Register as a dockable pane (done by nuke_plugin/menu.py):
    nukescripts.panels.registerWidgetAsPanel("st_roto_nuke.panel.ObjectPanel", "ST-ROTO Objects", "st_roto.objects")
"""
from __future__ import annotations

try:
    from PySide6 import QtWidgets
except ImportError:                       # Nuke 13-15 ship PySide2
    from PySide2 import QtWidgets

import nuke

from st_roto import views
from . import collab
from . import node as stnode
from . import session

COLUMNS = ["name", "origin", "locked", "held by", "keys", "frames", "review"]


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
        btns = QtWidgets.QHBoxLayout()
        for label, fn in (("Rename", self.rename), ("Lock / Unlock", self.toggle_lock), ("Delete", self.delete),
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
            for j, v in enumerate([r["name"], r["origin"], "yes" if r["locked"] else "", held, str(r["keys"]), frames,
                                   review]):
                item = QtWidgets.QTableWidgetItem(v)
                if j == 6 and flags:
                    item.setToolTip("\n".join("frame %d [%s]: %s" % fr for fr in flags))
                self.table.setItem(i, j, item)
        self.info.setText("%d objects · undo %s · redo %s" % (len(self.rows), "yes" if bus.can_undo() else "no",
                                                            "yes" if bus.can_redo() else "no"))
        try:
            self.collab_info.setText(collab.status_line(path))
        except Exception as e:                                # noqa: BLE001
            self.collab_info.setText("collaboration: %s" % e)

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
