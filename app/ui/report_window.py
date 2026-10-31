"""Reusable report screen: date range, search, table, Excel/CSV export, PDF print."""
from pathlib import Path

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QDateEdit, QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout)

from ..reports import export
from ..services import masters
from .printing import open_file
from .widgets import make_table


class ReportWindow(QDialog):
    """`builder(db, date_from, date_to)` (or `builder(db)` when use_dates=False) returns a report dict."""

    def __init__(self, db, builder, title, use_dates=True, actions=None, parent=None):
        super().__init__(parent)
        self.db, self.builder, self.use_dates = db, builder, use_dates
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

    def _range(self):
        return (self.d_from.date().toString("yyyy-MM-dd"), self.d_to.date().toString("yyyy-MM-dd"))

    def reload(self):
        if self.use_dates:
            f, t = self._range()
            if f > t:
                QMessageBox.warning(self, "Dates", "'From' date is after 'To' date.")
                return
            self.report = self.builder(self.db, f, t)
        else:
            self.report = self.builder(self.db)
        self._render()

    def _filtered(self):
        """Report with only the rows matching the search box (bold rows such as totals always stay)."""
        rep = self.report
        text = self.search.text().strip().lower()
        if not text:
            return rep
        keep = [i for i, r in enumerate(rep["rows"]) if i in rep["bold_rows"] or any(text in str(c).lower() for c in r)]
        return {**rep, "rows": [rep["rows"][i] for i in keep],
                "bold_rows": {n for n, i in enumerate(keep) if i in rep["bold_rows"]}}

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
