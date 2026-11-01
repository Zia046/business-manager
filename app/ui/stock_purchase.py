"""Stock Purchase window: the purchase price is always typed by the user."""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractItemDelegate, QAbstractItemView, QApplication, QDoubleSpinBox, QGridLayout,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget, QMessageBox, QPlainTextEdit,
                               QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout)

from ..services import masters, trading
from ..services.common import BusinessError, supplier_balance
from .enter_safe import EnterSafeDialog
from .imei_dialogs import ask_purchase_imeis
from .parties import PartyForm
from .party_picker import combo_party_id, make_party_combo
from .printing import print_purchase
from .products import ProductForm
from .purchase_model import PurchaseDraft
from .widgets import money

COLS = ["ID", "Product", "In stock", "Quantity Purchase", "Purchase Price", "Amount", "Remove"]
C_ID, C_NAME, C_STOCK, C_QTY, C_PRICE, C_AMT, C_DEL = range(7)
EDIT_ORDER = (C_QTY, C_PRICE)


class StockPurchaseDialog(EnterSafeDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.draft = PurchaseDraft()
        self._stock = {}
        self._loading = False
        self.setWindowTitle("Stock Purchase")
        self.resize(980, 660)
        self._build()
        self._recalc()
        self.search.setFocus()

    def _build(self):
        root = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QLabel("Supplier:"))
        self.supplier = make_party_combo(self.db, "supplier")
        self.supplier.currentIndexChanged.connect(self._supplier_changed)
        row.addWidget(self.supplier)
        b = QPushButton("New Supplier")
        b.setObjectName("secondary")
        b.clicked.connect(self._new_supplier)
        row.addWidget(b)
        self.sup_info = QLabel()
        self.sup_info.setObjectName("subtitle")
        row.addWidget(self.sup_info)
        row.addStretch()
        root.addLayout(row)

        srow = QHBoxLayout()
        self.search = QLineEdit(placeholderText="Search existing product: name, #tag, ID... (Enter = add)")
        self.search.textChanged.connect(self._search_products)
        self.search.returnPressed.connect(self._add_from_search)
        srow.addWidget(self.search)
        newp = QPushButton("+ New Product")
        newp.setObjectName("secondary")
        newp.clicked.connect(self._new_product)
        srow.addWidget(newp)
        root.addLayout(srow)
        self.results = QListWidget()
        self.results.setMaximumHeight(110)
        self.results.itemDoubleClicked.connect(lambda _: self._add_from_search())
        root.addWidget(self.results)

        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        for c, w in ((C_ID, 50), (C_NAME, 330), (C_STOCK, 90), (C_QTY, 90), (C_PRICE, 200), (C_AMT, 130), (C_DEL, 90)):
            self.table.setColumnWidth(c, w)
        self.table.itemChanged.connect(self._cell_changed)
        self.table.itemDelegate().closeEditor.connect(self._editor_closed)
        root.addWidget(self.table, 1)

        bottom = QHBoxLayout()
        left = QVBoxLayout()
        left.addWidget(QLabel("Note:"))
        self.note = QPlainTextEdit()
        self.note.setMaximumHeight(70)
        left.addWidget(self.note)
        self.warn = QLabel()
        self.warn.setObjectName("error")
        self.warn.setWordWrap(True)
        left.addWidget(self.warn)
        left.addStretch()
        bottom.addLayout(left, 3)
        grid = QGridLayout()
        self.total_lbl = QLabel("0.00")
        self.total_lbl.setStyleSheet("font-size: 28px; font-weight: 800; color: #1b6ef3;")
        self.paid = QDoubleSpinBox()
        self.paid.setRange(0, 1e9)
        self.paid.setDecimals(2)
        self.paid.setGroupSeparatorShown(True)
        self.paid.setEnabled(False)          # purchases are always saved as fully paid
        self.balance_lbl = QLabel("0.00")
        self.balance_lbl.setStyleSheet("font-weight: 700; font-size: 16px;")
        for i, (t, w) in enumerate((("TOTAL", self.total_lbl), ("Paid (automatic, full)", self.paid),
                                    ("Balance", self.balance_lbl))):
            grid.addWidget(QLabel(t), i, 0)
            grid.addWidget(w, i, 1, Qt.AlignRight)
        bottom.addLayout(grid, 2)
        root.addLayout(bottom)

        btns = QHBoxLayout()
        btns.addStretch()
        close = QPushButton("Close")
        close.setObjectName("secondary")
        close.clicked.connect(self.reject)
        save = QPushButton("Save")
        save.clicked.connect(lambda: self._save(False))
        sp = QPushButton("Save && Print  (Ctrl+P)")
        sp.clicked.connect(lambda: self._save(True))
        for x in (close, save, sp):
            btns.addWidget(x)
        root.addLayout(btns)
        QShortcut(QKeySequence("Ctrl+P"), self, activated=lambda: self._save(True))
        QShortcut(QKeySequence("Ctrl+S"), self, activated=lambda: self._save(False))

    # ---- supplier ----
    def _supplier_changed(self, *_):
        pid = combo_party_id(self.supplier)
        self.sup_info.setText(f"We owe: {money(supplier_balance(self.db.conn, pid))}" if pid else "")

    def _new_supplier(self):
        f = PartyForm(self.db, "supplier", parent=self)
        if f.exec():
            make_party_combo(self.db, "supplier", select_id=f.saved_id, combo=self.supplier)
            self._supplier_changed()

    # ---- products ----
    def _search_products(self, text):
        self.results.clear()
        if not text.strip():
            return
        for p in masters.search_products(self.db, text, limit=30):
            self.results.addItem(f"{p['id']}  |  {p['name']}   (stock {p['stock']:g})")
            self.results.item(self.results.count() - 1).setData(Qt.UserRole, p)
        if self.results.count():
            self.results.setCurrentRow(0)

    def _new_product(self):
        f = ProductForm(self.db, parent=self)
        if f.exec():
            p = masters.search_products(self.db, str(f.saved_id))[0]
            self._add_product(p)

    def _add_from_search(self):
        item = self.results.currentItem()
        if item:
            self._add_product(item.data(Qt.UserRole))
            self.search.clear()
            self.results.clear()

    def _add_product(self, p):
        serials = []
        if p["track_serial"]:
            # a phone cannot be saved without its IMEI number(s)
            units = ask_purchase_imeis(self, p["name"], p["imei_mode"], checker=self._check_units)
            if not units:
                return
            serials = units
        self._stock[p["id"]] = p["stock"]
        ln = self.draft.add_product(p, serials)
        idx = self.draft.lines.index(ln)
        self._refresh_table()
        QTimer.singleShot(0, lambda: self._edit_cell(idx, C_QTY if not ln["track_serial"] else C_PRICE))

    def _check_units(self, units):
        used = self.draft.imeis_in_use()
        for u in units:
            for x in u:
                if x and x in used:
                    raise BusinessError(f"IMEI {x} is already on this purchase")
                if x and self.db.scalar("SELECT COUNT(*) FROM serials WHERE serial=? OR imei2=?", (x, x)):
                    raise BusinessError(f"IMEI {x} already exists in the stock")

    def _refresh_table(self):
        self._loading = True
        self.table.setRowCount(len(self.draft.lines))
        for r, ln in enumerate(self.draft.lines):
            price_txt = "" if ln["price"] is None else f"{ln['price']:.2f}"
            name = ln["name"] + (f"  [{len(ln['serials'])} phone(s) with IMEI]" if ln["serials"] else "")
            cells = [(C_ID, str(ln["product_id"]), False), (C_NAME, name, False),
                     (C_STOCK, f"{self._stock.get(ln['product_id'], 0):g}", False),
                     (C_QTY, f"{ln['qty']:g}", not ln["track_serial"]), (C_PRICE, price_txt, True),
                     (C_AMT, money(PurchaseDraft.line_amount(ln)), False)]
            for col, text, editable in cells:
                it = QTableWidgetItem(text)
                it.setFlags(it.flags() | Qt.ItemIsEditable if editable else it.flags() & ~Qt.ItemIsEditable)
                if col >= C_STOCK:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if col == C_PRICE and ln["price"] is None:
                    it.setBackground(QColor("#fff4d6"))  # price still to be typed
                self.table.setItem(r, col, it)
            rm = QPushButton("Remove")
            rm.setObjectName("secondary")
            rm.setAutoDefault(False)
            rm.clicked.connect(lambda _=False, i=r: self._remove(i))
            self.table.setCellWidget(r, C_DEL, rm)
        self._loading = False
        self._recalc()

    def _remove(self, i):
        if 0 <= i < len(self.draft.lines):
            del self.draft.lines[i]
            self._refresh_table()

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
                if v < 0 or (item.column() == C_QTY and v == 0):
                    raise ValueError
                ln["price" if item.column() == C_PRICE else "qty"] = v
        except ValueError:
            self.warn.setText("Enter a valid positive number.")
        QTimer.singleShot(0, self._refresh_table)     # rebuild after the edit has finished

    # ---- Enter walks Qty -> Price -> back to the search box ----
    def _editor_closed(self, editor, hint):
        if hint == QAbstractItemDelegate.EndEditHint.SubmitModelCache:
            QTimer.singleShot(0, self._next_cell)

    def _next_cell(self):
        row, col = self.table.currentRow(), self.table.currentColumn()
        later = [c for c in EDIT_ORDER if c > col]
        if row >= 0 and later and self._edit_cell(row, later[0]):
            return
        self.search.setFocus()
        self.search.selectAll()

    def _edit_cell(self, row, col) -> bool:
        for c in [x for x in EDIT_ORDER if x >= col]:
            it = self.table.item(row, c)
            if it is not None and it.flags() & Qt.ItemIsEditable:
                self.table.setFocus()
                self.table.setCurrentCell(row, c)
                self.table.editItem(it)
                return True
        return False

    def _recalc(self, *_):
        total = self.draft.total()
        self.total_lbl.setText(money(total))
        self.paid.setValue(total)                      # saved as fully paid
        self.balance_lbl.setText(money(0))
        miss = self.draft.missing_prices()
        self.warn.setText("Type the purchase price for: " + ", ".join(ln["name"] for ln in miss) if miss else "")

    # ---- save ----
    def _save(self, print_after):
        sid = combo_party_id(self.supplier)
        if not sid:
            QMessageBox.warning(self, "Supplier", "Please select a supplier.")
            return
        if self.draft.missing_prices():
            QMessageBox.warning(self, "Price missing", "Type the purchase price for every product.")
            return
        if self.draft.serial_mismatch():
            QMessageBox.warning(self, "IMEI", "IMEI count must match the quantity.")
            return
        try:
            pid = trading.create_purchase(self.db, sid, self.draft.service_items(), paid=self.draft.total(),
                                          note=self.note.toPlainText().strip())
        except BusinessError as exc:
            QMessageBox.warning(self, "Cannot save", str(exc))
            return
        no = self.db.scalar("SELECT no FROM purchases WHERE id=?", (pid,), "")
        if print_after:
            try:
                print_purchase(self.db, pid)
            except Exception as exc:
                QMessageBox.warning(self, "Print", f"Purchase {no} was saved, but printing failed:\n{exc}")
        else:
            QMessageBox.information(self, "Saved", f"Purchase {no} saved. Stock updated.")
        self.draft = PurchaseDraft()
        self._stock.clear()
        self.paid.setValue(0)
        self.note.clear()
        make_party_combo(self.db, "supplier", combo=self.supplier)
        self._supplier_changed()
        self._refresh_table()
        self.search.setFocus()
