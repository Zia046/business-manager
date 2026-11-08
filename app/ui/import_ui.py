"""New Account > Import from Excel."""
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout)

from ..config import APP_NAME
from ..services import importer
from ..services.common import BusinessError
from .enter_safe import EnterSafeDialog
from .widgets import make_table, set_row

KINDS = [("Products", "products"), ("Customers", "customers"), ("Suppliers", "suppliers")]
COLORS = {"new": QColor("#DCFCE7"), "skip": QColor("#F3F5F9"), "error": QColor("#FEE2E2")}


class ImportDialog(EnterSafeDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db, self.rows = db, []
        self.setWindowTitle("Import from Excel / CSV")
        self.resize(820, 560)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("1. Download the template, fill it in Excel.   2. Choose your file.   "
                             "3. Check the preview, then press Import."))
        row = QHBoxLayout()
        self.kind = QComboBox()
        for label, key in KINDS:
            self.kind.addItem(label, key)
        self.kind.currentIndexChanged.connect(self._preview)
        tpl = QPushButton("Download Template")
        tpl.setObjectName("secondary")
        tpl.clicked.connect(self.template)
        pick = QPushButton("Choose File...")
        pick.clicked.connect(self.choose)
        row.addWidget(QLabel("Import:"))
        row.addWidget(self.kind)
        row.addWidget(tpl)
        row.addWidget(pick)
        row.addStretch()
        lay.addLayout(row)
        self.file_lbl = QLabel("No file chosen")
        self.file_lbl.setObjectName("subtitle")
        lay.addWidget(self.file_lbl)
        self.table = make_table(["Line", "Name", "Result", "Message"], stretch_col=3)
        lay.addWidget(self.table)
        self.summary = QLabel("")
        self.summary.setStyleSheet("font-weight: 700;")
        lay.addWidget(self.summary)
        btns = QHBoxLayout()
        btns.addStretch()
        close = QPushButton("Close")
        close.setObjectName("secondary")
        close.clicked.connect(self.reject)
        self.go = QPushButton("Import")
        self.go.setEnabled(False)
        self.go.clicked.connect(self.run)
        btns.addWidget(close)
        btns.addWidget(self.go)
        lay.addLayout(btns)

    def _kind(self):
        return self.kind.currentData()

    def template(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save template", f"{self._kind()}_template.xlsx", "Excel (*.xlsx)")
        if path:
            importer.write_template(path, self._kind())
            QMessageBox.information(self, APP_NAME, f"Template saved:\n{path}")

    def choose(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose file", "", "Excel / CSV (*.xlsx *.csv)")
        if not path:
            return
        try:
            self.rows = importer.read_rows(path)
        except Exception as exc:
            QMessageBox.warning(self, "File", f"Could not read the file:\n{exc}")
            return
        self.file_lbl.setText(path)
        self._preview()

    def _run(self, dry):
        if self._kind() == "products":
            return importer.import_products(self.db, self.rows, dry_run=dry)
        return importer.import_parties(self.db, self.rows, self._kind()[:-1], dry_run=dry)

    def _preview(self, *_):
        self.table.setRowCount(0)
        self.go.setEnabled(False)
        if not self.rows:
            return
        try:
            res = self._run(True)
        except BusinessError as exc:
            self.summary.setText(str(exc))
            return
        self._show(res)
        n = sum(r["status"] == "new" for r in res)
        self.go.setEnabled(n > 0)

    def _show(self, res):
        self.table.setRowCount(len(res))
        for i, r in enumerate(res):
            set_row(self.table, i, [r["line"], r["name"], {"new": "Will add", "skip": "Skip", "error": "Error",
                                                           "done": "Added"}[r["status"]], r["message"]],
                    (), COLORS.get(r["status"]))
        c = {k: sum(r["status"] == k for r in res) for k in ("new", "skip", "error")}
        self.summary.setText(f"Will add: {c['new']}     Skipped (already exist): {c['skip']}     Errors: {c['error']}")

    def run(self):
        try:
            res = self._run(False)
        except BusinessError as exc:
            QMessageBox.warning(self, "Import", str(exc))
            return
        added = sum(r["status"] == "new" for r in res)
        errors = sum(r["status"] == "error" for r in res)
        for r in res:
            if r["status"] == "new":
                r["status"] = "done"
        self._show(res)
        self.go.setEnabled(False)
        self.rows = []
        QMessageBox.information(self, APP_NAME, f"{added} added.   {errors} row(s) had errors and were not imported.")
