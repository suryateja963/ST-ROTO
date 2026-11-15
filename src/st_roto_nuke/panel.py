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
from . import node as stnode
from . import session

COLUMNS = ["name", "origin", "locked", "keys", "frames"]


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
        self.info = QtWidgets.QLabel("select an ST_Roto node and press 'Use selected ST_Roto node'")
        self.info.setWordWrap(True)
        lay.addWidget(self.info)

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
        self.rows = views.object_rows(store, shot) if shot else []
        self.table.setRowCount(len(self.rows))
        for i, r in enumerate(self.rows):
            frames = "" if r["first"] is None else "%d-%d" % (r["first"], r["last"])
            for j, v in enumerate([r["name"], r["origin"], "yes" if r["locked"] else "", str(r["keys"]), frames]):
                self.table.setItem(i, j, QtWidgets.QTableWidgetItem(v))
        self.info.setText("%d objects · undo %s · redo %s" % (len(self.rows), "yes" if bus.can_undo() else "no",
                                                            "yes" if bus.can_redo() else "no"))

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
        return self._do(lambda bus: bus.execute({"op": "update_object", "id": r["id"], "fields": {"name": new_name}}))

    def toggle_lock(self):
        r = self._selected()
        return self._do(lambda bus: bus.execute({"op": "update_object", "id": r["id"],
                                                 "fields": {"locked": 0 if r["locked"] else 1}}))

    def delete(self):
        r = self._selected()
        return self._do(lambda bus: bus.execute({"op": "delete_subtree", "object_id": r["id"]}))

    def undo(self):
        return self._do(lambda bus: bus.undo())

    def redo(self):
        return self._do(lambda bus: bus.redo())
