"""Barcode / price labels: choose products and how many labels of each, then print."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QMessageBox, QPushButton,
                               QSpinBox, QVBoxLayout)

from ..services import masters
from .enter_safe import EnterSafeDialog
from .printing import print_labels
from .widgets import make_table, money, set_row


class LabelsDialog(EnterSafeDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.items = []                       # [product dict, copies]
        self.setWindowTitle("Barcode / Price Labels")
        self.resize(900, 640)
        lay = QVBoxLayout(self)
        self.search = QLineEdit(placeholderText="Search product (name, #tag, ID or scan the barcode) - Enter = add")
        self.search.textChanged.connect(self._search)
        self.search.returnPressed.connect(self._add)
        lay.addWidget(self.search)
        self.results = QListWidget()
        self.results.setMaximumHeight(110)
        self.results.itemDoubleClicked.connect(lambda _: self._add())
        lay.addWidget(self.results)
        self.table = make_table(["ID", "Product", "Price", "Barcode", "Labels"], stretch_col=1)
        lay.addWidget(self.table, 1)
        row = QHBoxLayout()
        self.copies = QSpinBox()
        self.copies.setRange(1, 500)
        self.copies.setValue(1)
        self.copies.setPrefix("Labels per product: ")
        self.layout_box = QComboBox()
        self.layout_box.addItem("A4 sticker sheet (3 x 7 labels)", "sheet")
        self.layout_box.addItem("Label printer roll (50 x 30 mm)", "roll")
        row.addWidget(self.copies)
        row.addWidget(self.layout_box)
        row.addStretch()
        remove = QPushButton("Remove Selected")
        remove.setObjectName("secondary")
        remove.clicked.connect(self._remove)
        clear = QPushButton("Clear")
        clear.setObjectName("secondary")
        clear.clicked.connect(self._clear)
        close = QPushButton("Close")
        close.setObjectName("secondary")
        close.clicked.connect(self.reject)
        go = QPushButton("Print Labels")
        go.clicked.connect(self._print)
        for b in (remove, clear, close, go):
            row.addWidget(b)
        lay.addLayout(row)
        self.hint = QLabel("A product without its own barcode is labelled with its 6-digit ID.")
        self.hint.setObjectName("subtitle")
        lay.addWidget(self.hint)

    def _search(self, text):
        self.results.clear()
        if not text.strip():
            return
        for p in masters.search_products(self.db, text, limit=30):
            self.results.addItem(f"{p['id']}  |  {p['name']}   {money(p['sale_price'])}")
            self.results.item(self.results.count() - 1).setData(Qt.UserRole, p)
        if self.results.count():
            self.results.setCurrentRow(0)

    def _add(self):
        item = self.results.currentItem()
        if not item:
            return
        p = item.data(Qt.UserRole)
        for it in self.items:
            if it[0]["id"] == p["id"]:
                it[1] += self.copies.value()
                break
        else:
            self.items.append([p, self.copies.value()])
        self.search.clear()
        self.results.clear()
        self._render()
        self.search.setFocus()

    def _render(self):
        self.table.setRowCount(len(self.items))
        for i, (p, n) in enumerate(self.items):
            set_row(self.table, i, [p["id"], p["name"], money(p["sale_price"]), masters.barcode_for(p), n], (2, 4))

    def _remove(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        for r in rows:
            del self.items[r]
        self._render()

    def _clear(self):
        self.items = []
        self._render()

    def _print(self):
        if not self.items:
            QMessageBox.information(self, "Labels", "Add at least one product first.")
            return
        try:
            print_labels(self.db, [(p["id"], n) for p, n in self.items], self.layout_box.currentData())
        except Exception as exc:
            QMessageBox.warning(self, "Labels", f"Could not print the labels:\n{exc}")
