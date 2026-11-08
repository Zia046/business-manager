"""'Select from list': the whole inventory in one window with search, stock and (owner only) purchase prices."""
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout)

from ..services import masters
from ..services.common import is_owner
from .picker_rows import picker_columns, picker_row

LIMIT = 500


class ProductPickerDialog(QDialog):
    def __init__(self, db, parent=None, text=""):
        super().__init__(parent)
        self.db = db
        self.owner = is_owner()
        self.chosen = None
        self.setWindowTitle("Select product from inventory")
        self.resize(900, 560)
        lay = QVBoxLayout(self)
        self.search = QLineEdit(text, placeholderText="Search: name, #tag, ID, category or similar spelling...")
        self.search.textChanged.connect(self._load)
        self.search.installEventFilter(self)
        lay.addWidget(self.search)
        cols = picker_columns(self.owner)
        self.table = QTableWidget(0, len(cols))
        self.table.setHorizontalHeaderLabels(cols)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.cellActivated.connect(lambda r, c: self._pick(r))      # Enter or double-click
        self.table.cellDoubleClicked.connect(lambda r, c: self._pick(r))
        lay.addWidget(self.table, 1)
        self.info = QLabel("")
        self.info.setObjectName("subtitle")
        lay.addWidget(self.info)
        row = QHBoxLayout()
        ok = QPushButton("Select")
        ok.setDefault(True)
        ok.clicked.connect(lambda: self._pick(self.table.currentRow()))
        cancel = QPushButton("Cancel")
        cancel.setObjectName("secondary")
        cancel.clicked.connect(self.reject)
        row.addStretch()
        row.addWidget(ok)
        row.addWidget(cancel)
        lay.addLayout(row)
        self._load()
        self.search.setFocus()

    def _load(self, *_):
        text = self.search.text()
        rows = masters.search_products(self.db, text, limit=LIMIT)
        self.table.setRowCount(0)
        for p in rows:
            self.table.insertRow(self.table.rowCount())
            r = self.table.rowCount() - 1
            for c, val in enumerate(picker_row(p, self.owner)):
                it = QTableWidgetItem(val)
                if c >= 3:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if c == 3 and p["stock"] <= 0:
                    it.setForeground(QColor("#DC2626"))              # out of stock
                if c == 1:
                    it.setData(Qt.UserRole, p)
                self.table.setItem(r, c, it)
        if rows:
            self.table.selectRow(0)
        self.info.setText(f"{len(rows)} product(s)" + ("  (type more letters to narrow down)" if len(rows) >= LIMIT else "")
                          + "   |   Enter or double-click = select")

    def eventFilter(self, obj, ev):
        if obj is self.search and ev.type() == QEvent.KeyPress:
            if ev.key() in (Qt.Key_Down, Qt.Key_Up):
                self.table.setFocus()
                return False
            if ev.key() in (Qt.Key_Return, Qt.Key_Enter):
                self._pick(self.table.currentRow())
                return True
        return super().eventFilter(obj, ev)

    def keyPressEvent(self, ev):
        if ev.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._pick(self.table.currentRow())
            return
        super().keyPressEvent(ev)

    def _pick(self, row):
        if row is None or row < 0 or self.table.item(row, 1) is None:
            return
        self.chosen = self.table.item(row, 1).data(Qt.UserRole)
        self.accept()
