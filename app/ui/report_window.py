"""Reusable report screen: date range, search, table, Excel/CSV export, PDF print."""
from pathlib import Path

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (QComboBox, QCompleter, QDateEdit, QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout)

from ..reports import export
from ..services import masters
from .printing import open_file
from .party_picker import combo_party_id, make_party_combo
from .widgets import make_table


class ReportWindow(QDialog):
    """`builder(db, date_from, date_to)` (or `builder(db)` when use_dates=False) returns a report dict."""

    def __init__(self, db, builder, title, use_dates=True, actions=None, parent=None, filter_kind=None):
        """filter_kind: None, 'customer', 'supplier' or 'product' - adds a picker; its id is passed
        to the builder as the last argument."""
        super().__init__(parent)
        self.db, self.builder, self.use_dates, self.filter_kind = db, builder, use_dates, filter_kind
        self.filter_combo = None
        self.report = None
        self.setWindowTitle(title)
        self.resize(1050, 650)
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        if use_dates:
            today = QDate.currentDate()
            self.d_from = QDateEdit(QDate(today.year(), today.month(), 1))
            self.d_to = QDateEdit(today)
            for w in (self.d_from, self.d_to):
                w.setCalendarPopup(True)
                w.setDisplayFormat("dd-MM-yyyy")
            top.addWidget(QLabel("From"))
            top.addWidget(self.d_from)
            top.addWidget(QLabel("To"))
            top.addWidget(self.d_to)
            show = QPushButton("Show")
            show.clicked.connect(self.reload)
            top.addWidget(show)
        if filter_kind == "imei":
            top.addWidget(QLabel("IMEI:"))
            self.filter_combo = QLineEdit(placeholderText="Type IMEI (3+ digits) and press Enter")
            self.filter_combo.setMinimumWidth(260)
            self.filter_combo.returnPressed.connect(self.reload)
            top.addWidget(self.filter_combo)
        elif filter_kind:
            top.addWidget(QLabel(filter_kind.title() + ":"))
            self.filter_combo = self._make_filter_combo(filter_kind)
            self.filter_combo.currentIndexChanged.connect(lambda *_: self.reload())
            top.addWidget(self.filter_combo)
        self.search = QLineEdit(placeholderText="Search in this report...")
        self.search.textChanged.connect(self._render)
        top.addWidget(self.search, 1)
        for text, fn in (("Excel", self.to_excel), ("CSV", self.to_csv), ("Print / PDF", self.to_pdf)):
            b = QPushButton(text)
            b.setObjectName("secondary")
            b.clicked.connect(fn)
            top.addWidget(b)
        for text, fn in (actions or []):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, f=fn: f(self))
            top.addWidget(b)
        lay.addLayout(top)
        self.table = make_table([""], stretch_col=0)
        lay.addWidget(self.table)
        self.summary = QLabel()
        self.summary.setStyleSheet("font-weight: 700; font-size: 14px;")
        lay.addWidget(self.summary)
        self.reload()

    def _make_filter_combo(self, kind):
        if kind in ("customer", "supplier"):
            return make_party_combo(self.db, kind)
        combo = QComboBox()
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.NoInsert)
        combo.setMinimumWidth(320)
        rows = self.db.query("SELECT id, name FROM products WHERE active=1 ORDER BY name LIMIT 5000")
        for r in rows:
            combo.addItem(f"{r['name']}  (ID {r['id']})", r["id"])
        comp = QCompleter([combo.itemText(i) for i in range(combo.count())], combo)
        comp.setCaseSensitivity(Qt.CaseInsensitive)
        comp.setFilterMode(Qt.MatchContains)
        combo.setCompleter(comp)
        combo.setCurrentIndex(-1)
        return combo

    def _filter_id(self):
        if self.filter_kind == "imei":
            return self.filter_combo.text().strip()
        return combo_party_id(self.filter_combo) if self.filter_combo is not None else None

    def _range(self):
        return (self.d_from.date().toString("yyyy-MM-dd"), self.d_to.date().toString("yyyy-MM-dd"))

    def reload(self):
        if self.use_dates:
            f, t = self._range()
            if f > t:
                QMessageBox.warning(self, "Dates", "'From' date is after 'To' date.")
                return
            args = (self._filter_id(),) if self.filter_kind else ()
            self.report = self.builder(self.db, f, t, *args)
        else:
            args = (self._filter_id(),) if self.filter_kind else ()
            self.report = self.builder(self.db, *args)
        self._render()

    def _filtered(self):
        """Report with only the rows matching the search box (bold rows such as totals always stay)."""
        rep = self.report
        text = self.search.text().strip().lower()
        if not text:
            return rep
        keep = [i for i, r in enumerate(rep["rows"]) if i in rep["bold_rows"] or any(text in str(c).lower() for c in r)]
        low = rep.get("low_rows", set())
        return {**rep, "rows": [rep["rows"][i] for i in keep],
                "bold_rows": {n for n, i in enumerate(keep) if i in rep["bold_rows"]},
                "low_rows": {n for n, i in enumerate(keep) if i in low}}

    def _render(self, *_):
        if not self.report:
            return
        rep = self._filtered()
        self.setWindowTitle(rep["title"])
        t: QTableWidget = self.table
        t.clear()
        t.setColumnCount(len(rep["headers"]))
        t.setHorizontalHeaderLabels(rep["headers"])
        t.setRowCount(len(rep["rows"]))
        bold = QFont()
        bold.setBold(True)
        for r, row in enumerate(rep["rows"]):
            for c, v in enumerate(row):
                it = QTableWidgetItem(str(v))
                if c in rep["numeric"]:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if r in rep["bold_rows"]:
                    it.setFont(bold)
                if r in rep.get("low_rows", ()):
                    it.setBackground(QColor("#FFE3DF"))  # low stock
                t.setItem(r, c, it)
        t.resizeColumnsToContents()
        t.horizontalHeader().setStretchLastSection(True)
        self.summary.setText("      ".join(f"{a}: {b}" for a, b in rep["summary"]))

    def selected_first_cell(self):
        rows = self.table.selectionModel().selectedRows()
        return self.table.item(rows[0].row(), 0).text() if rows else None

    # ---- output ----
    def _out_dir(self) -> Path:
        d = Path(self.db.data_dir) / "reports"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _save_as(self, ext, label):
        name = f"{self.report['title'].replace(' ', '_')}.{ext}"
        path, _ = QFileDialog.getSaveFileName(self, "Save", str(self._out_dir() / name), label)
        return path

    def to_excel(self):
        path = self._save_as("xlsx", "Excel (*.xlsx)")
        if path:
            export.export_xlsx(self._filtered(), path)
            QMessageBox.information(self, "Saved", f"Saved to:\n{path}")

    def to_csv(self):
        path = self._save_as("csv", "CSV (*.csv)")
        if path:
            export.export_csv(self._filtered(), path)
            QMessageBox.information(self, "Saved", f"Saved to:\n{path}")

    def to_pdf(self):
        path = self._out_dir() / f"{self.report['title'].replace(' ', '_')}.pdf"
        try:
            export.build_table_pdf(self._filtered(), masters.get_company(self.db), path)
            open_file(path)
        except Exception as exc:
            QMessageBox.warning(self, "Print", f"Could not create the PDF:\n{exc}")
