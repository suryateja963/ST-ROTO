"""ST-ROTO Models panel (dockable; T-101, REQ-052 / REQ-130). Shows every model in every storage location with its
licence, approval, revision, source and GPU fit; Verify / Self-test / Remove / Import. Logic: models_ui.py.
Registered by nuke_plugin/menu.py as "ST-ROTO Models". Downloads are not done here (owner-approved tool only)."""
from __future__ import annotations

try:
    from PySide6 import QtWidgets
except ImportError:                       # Nuke 13-15 ship PySide2
    from PySide2 import QtWidgets

from . import models_ui

COLUMNS = ["model", "location", "used", "licence", "approval", "revision", "installed", "GPU memory", "source"]


class ModelPanel(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []
        lay = QtWidgets.QVBoxLayout(self)
        self.table = QtWidgets.QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        lay.addWidget(self.table)
        btns = QtWidgets.QHBoxLayout()
        for label, fn, tip in (
                ("Refresh", self.refresh, "Look at every model location again."),
                ("Verify", self.verify, "Recompute the SHA-256 of every file of the selected model (can take a minute)."),
                ("Self-test", self.self_test, "Track a generated moving disc with the selected model on this machine: "
                                              "accuracy and time per frame."),
                ("Remove...", self.remove, "Delete the selected copy's files (its manifests stay as the record)."),
                ("Import...", self.import_model, "Copy an approved model from another models folder into your user "
                                                 "location (refused unless licence, approval and checksums are right).")):
            b = QtWidgets.QPushButton(label); b.setToolTip(tip); b.clicked.connect(fn); btns.addWidget(b)
        lay.addLayout(btns)
        self.info = QtWidgets.QLabel("")
        self.info.setWordWrap(True)
        lay.addWidget(self.info)
        self.refresh()

    def refresh(self):
        try:
            self.rows = models_ui.rows()
        except Exception as e:                                # noqa: BLE001
            self.info.setText("error: %s" % e); return
        self.table.setRowCount(len(self.rows))
        for i, r in enumerate(self.rows):
            vals = [r["name"], r.get("location", ""), "yes" if r.get("active") else "", r["licence"] or "",
                    r["approval"] or "", (r["revision"] or "")[:10], "yes" if r["exports_present"] else "no",
                    r.get("vram", ""), r["repo"] or ""]
            for j, v in enumerate(vals):
                item = QtWidgets.QTableWidgetItem(str(v))
                if j == 3 and not r["usable"]:
                    item.setToolTip(r["reason"])
                self.table.setItem(i, j, item)
        self.info.setText("%d model copies; downloads only with owner approval (tools/models/download_models.py)"
                          % len(self.rows))

    def _selected(self):
        i = self.table.currentRow()
        if i < 0 or i >= len(self.rows):
            raise ValueError("select a model row first")
        return self.rows[i]

    def verify(self):
        try:
            r = self._selected()
            res = models_ui.verify(r["name"], r["root"])
        except Exception as e:                                # noqa: BLE001
            self.info.setText("error: %s" % e); return None
        bad = [f for f in res["files"] if not f["ok"]]
        self.info.setText("%s: %s (%d files, %.1f s)%s" % (r["name"], "all files verified" if res["ok"] else "PROBLEM",
                                                           len(res["files"]) - 1, res["seconds"],
                                                           "" if not bad else ": " + "; ".join(
                                                               "%s %s" % (f["file"], f["detail"]) for f in bad)))
        return res

    def self_test(self):
        try:
            r = self._selected()
            res = models_ui.self_test(r["name"])
        except Exception as e:                                # noqa: BLE001
            self.info.setText("error: %s" % e); return None
        self.info.setText("%s self-test: %s %s" % (r["name"], "PASSED" if res.get("ok") else "FAILED",
                                                   {k: v for k, v in res.items() if k != "ok"}))
        return res

    def remove(self, confirm=None):
        try:
            r = self._selected()
        except ValueError as e:
            self.info.setText("error: %s" % e); return None
        if confirm is None:
            confirm = QtWidgets.QMessageBox.question(
                self, "Remove model", "Delete the files of %s in the %s location?\n%s" % (r["name"], r["location"],
                                                                                         r["root"])) == \
                QtWidgets.QMessageBox.Yes
        if not confirm:
            return None
        gone = models_ui.remove(r["name"], r["root"])
        self.refresh()
        self.info.setText("removed %s (%d folders); manifests kept" % (r["name"], len(gone)))
        return gone

    def import_model(self, src_root=None, name=None):
        try:
            if src_root is None:
                src_root = QtWidgets.QFileDialog.getExistingDirectory(self, "Models folder to import from "
                                                                            "(with manifests/ and onnx/)")
                if not src_root:
                    return None
                name, ok = QtWidgets.QInputDialog.getText(self, "Import model", "model name")
                if not ok:
                    return None
            res = models_ui.import_from(src_root, name)
        except Exception as e:                                # noqa: BLE001
            self.info.setText("error: %s" % e); return None
        self.refresh()
        self.info.setText("imported %s (%d files) into %s" % (res["model"], res["files"], res["to"]))
        return res
