"""Sale Return and Purchase Return screens."""
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDoubleSpinBox, QGridLayout, QHBoxLayout,
                               QLabel, QLineEdit, QListWidget, QMessageBox, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout)

from ..services import masters, trading
from ..services.common import BusinessError
from .enter_safe import EnterSafeDialog
from .imei_dialogs import ask_sale_imei
from .party_picker import combo_party_id, make_party_combo
from .return_model import ReturnDraft
from .widgets import money

COLS = ["ID", "Product", "On document", "Can return", "Return Qty", "Price", "Amount"]
C_ID, C_NAME, C_DOC, C_MAX, C_QTY, C_PRICE, C_AMT = range(7)

CFG = {
    "sale": dict(title="Sale Return", kind="customer", party="Customer", doc="Original invoice",
                 money_label="Refund paid to customer now", total_label="Return total (reduces customer balance)"),
    "purchase": dict(title="Purchase Return", kind="supplier", party="Supplier", doc="Original purchase",
                     money_label="Cash received from supplier now", total_label="Return total (reduces what we owe)"),
}


class ReturnDialog(EnterSafeDialog):
    def __init__(self, db, kind, parent=None):
        super().__init__(parent)
        self.db, self.kind, self.cfg = db, kind, CFG[kind]
        self.draft = ReturnDraft(kind)
        self._loading = False
        self.setWindowTitle(self.cfg["title"])
        self.resize(1000, 680)
        root = QVBoxLayout(self)

        row = QHBoxLayout()
        row.addWidget(QLabel(self.cfg["party"] + ":"))
        self.party = make_party_combo(db, self.cfg["kind"])
        self.party.currentIndexChanged.connect(self._party_changed)
        row.addWidget(self.party)
        row.addWidget(QLabel(self.cfg["doc"] + ":"))
        self.doc = QComboBox()
        self.doc.setMinimumWidth(320)
        self.doc.currentIndexChanged.connect(self._doc_changed)
        row.addWidget(self.doc)
        row.addStretch()
        root.addLayout(row)

        self.search = QLineEdit(placeholderText="No original document? Search a product to return manually...")
        self.search.textChanged.connect(self._search)
        self.search.returnPressed.connect(self._add_manual)
        root.addWidget(self.search)
        self.results = QListWidget()
        self.results.setMaximumHeight(100)
        self.results.itemDoubleClicked.connect(lambda _: self._add_manual())
        root.addWidget(self.results)

        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        for c, w in ((C_ID, 50), (C_NAME, 340), (C_DOC, 110), (C_MAX, 110), (C_QTY, 110), (C_PRICE, 120), (C_AMT, 130)):
            self.table.setColumnWidth(c, w)
        self.table.itemChanged.connect(self._cell_changed)
        root.addWidget(self.table, 1)

        bottom = QHBoxLayout()
        left = QVBoxLayout()
        left.addWidget(QLabel("Note:"))
        self.note = QLineEdit()
        left.addWidget(self.note)
        self.warn = QLabel()
        self.warn.setObjectName("error")
        self.warn.setWordWrap(True)
        left.addWidget(self.warn)
        left.addStretch()
        bottom.addLayout(left, 3)
        grid = QGridLayout()
        self.total_lbl = QLabel("0.00")
        self.total_lbl.setStyleSheet("font-size: 26px; font-weight: 800; color: #1b6ef3;")
        self.cash = QDoubleSpinBox()
        self.cash.setRange(0, 1e9)
        self.cash.setDecimals(2)
        self.cash.setGroupSeparatorShown(True)
        grid.addWidget(QLabel(self.cfg["total_label"]), 0, 0)
        grid.addWidget(self.total_lbl, 0, 1, Qt.AlignRight)
        grid.addWidget(QLabel(self.cfg["money_label"]), 1, 0)
        grid.addWidget(self.cash, 1, 1, Qt.AlignRight)
        bottom.addLayout(grid, 2)
        root.addLayout(bottom)

        btns = QHBoxLayout()
        btns.addStretch()
        close = QPushButton("Close")
        close.setObjectName("secondary")
        close.clicked.connect(self.reject)
        save = QPushButton("Save Return")
        save.setDefault(True)
        save.clicked.connect(self._save)
        btns.addWidget(close)
        btns.addWidget(save)
        root.addLayout(btns)
        self._party_changed()

    # ---- party / document ----
    def _party_changed(self, *_):
        pid = combo_party_id(self.party)
        self.doc.blockSignals(True)
        self.doc.clear()
        self.doc.addItem("-- none (manual return) --", None)
        if pid:
            if self.kind == "sale":
                rows = self.db.query("SELECT id, no, date, total FROM invoices WHERE party_id=? AND status='active' "
                                     "ORDER BY id DESC LIMIT 200", (pid,))
            else:
                rows = self.db.query("SELECT id, no, date, total FROM purchases WHERE party_id=? AND status='active' "
                                     "ORDER BY id DESC LIMIT 200", (pid,))
            for r in rows:
                self.doc.addItem(f"{r['no']}   {r['date'][:10]}   {money(r['total'])}", r["id"])
        self.doc.blockSignals(False)
        self.draft.clear()
        self._doc_changed()

    def _doc_id(self):
        return self.doc.currentData()

    def _doc_changed(self, *_):
        doc = self._doc_id()
        self.draft.clear()
        manual = doc is None
        self.search.setEnabled(manual)
        self.results.setEnabled(manual)
        if doc is not None:
            self.draft.load_from_document(trading.returnable_items(self.db, self.kind, doc))
        self._refresh()

    # ---- manual add ----
    def _search(self, text):
        self.results.clear()
        if not text.strip():
            return
        for p in masters.search_products(self.db, text, limit=30):
            self.results.addItem(f"{p['id']}  |  {p['name']}")
            self.results.item(self.results.count() - 1).setData(Qt.UserRole, p)
        if self.results.count():
            self.results.setCurrentRow(0)

    def _add_manual(self):
        item = self.results.currentItem()
        if item and self._doc_id() is None:
            self.draft.add_manual(item.data(Qt.UserRole))
            self.search.clear()
            self.results.clear()
            self._refresh()

    # ---- table ----
    def _refresh(self):
        self._loading = True
        self.table.setRowCount(len(self.draft.lines))
        for r, ln in enumerate(self.draft.lines):
            price = "" if ln["price"] is None else f"{ln['price']:.2f}"
            cells = [(C_ID, str(ln["product_id"]), False), (C_NAME, ln["name"], False),
                     (C_DOC, "" if ln["doc_qty"] is None else f"{ln['doc_qty']:g}", False),
                     (C_MAX, "" if ln["max_qty"] is None else f"{ln['max_qty']:g}", False),
                     (C_QTY, f"{ln['qty']:g}", True), (C_PRICE, price, True),
                     (C_AMT, money(ReturnDraft.line_amount(ln)), False)]
            for col, text, editable in cells:
                it = QTableWidgetItem(text)
                it.setFlags(it.flags() | Qt.ItemIsEditable if editable else it.flags() & ~Qt.ItemIsEditable)
                if col >= C_DOC:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if col == C_PRICE and ln["price"] is None:
                    it.setBackground(QColor("#fff4d6"))
                self.table.setItem(r, col, it)
        self._loading = False
        self._recalc()

    def _cell_changed(self, item):
        if self._loading or item.row() >= len(self.draft.lines) or item.column() not in (C_QTY, C_PRICE):
            return
        ln = self.draft.lines[item.row()]
        text = item.text().replace(",", "").strip()
        try:
            if item.column() == C_PRICE and text == "":
                ln["price"] = None
            else:
                v = float(text)
                if v < 0:
                    raise ValueError
                ln["qty" if item.column() == C_QTY else "price"] = v
        except ValueError:
            self.warn.setText("Enter a valid positive number.")
        QTimer.singleShot(0, self._refresh)      # never rebuild the table inside itemChanged

    def _recalc(self):
        self.total_lbl.setText(money(self.draft.total()))
        self.warn.setText(" ".join(self.draft.problems()) if self.draft.active() else "")

    # ---- save ----
    def _save(self):
        pid = combo_party_id(self.party)
        if not pid:
            QMessageBox.warning(self, self.cfg["title"], f"Please select a {self.cfg['party'].lower()}.")
            return
        problems = self.draft.problems() + self.draft.problems_phones()
        if problems:
            QMessageBox.warning(self, "Check the return", "\n".join(problems))
            return
        doc = self._doc_id()
        units = {}
        for ln in self.draft.phone_lines():          # every returned phone is identified by its IMEI
            got, n = [], int(ln["qty"])
            for k in range(n):
                title = f"IMEI of returned phone {k + 1} of {n}"
                one = ask_sale_imei(self, ln["name"], ln.get("imei_mode") or "single", None, title)
                if one is None:
                    return
                if one in got:
                    QMessageBox.warning(self, "Same phone", "This phone is already entered in this return.")
                    return
                got.append(one)
            units[ln["product_id"]] = got
        items = self.draft.service_items(units)
        try:
            if self.kind == "sale":
                trading.sale_return(self.db, pid, items, self.cash.value(), doc, self.note.text())
            else:
                trading.purchase_return(self.db, pid, items, self.cash.value(), doc, self.note.text())
        except BusinessError as exc:
            QMessageBox.warning(self, "Cannot save", str(exc))
            return
        QMessageBox.information(self, "Saved", "Return saved. Stock and account balance updated.")
        self.cash.setValue(0)
        self.note.clear()
        self._party_changed()
