"""Sale Invoice window (new invoice, or edit a saved one)."""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractItemDelegate, QAbstractItemView, QApplication, QCheckBox, QComboBox,
                               QCompleter, QDoubleSpinBox, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QListWidget, QMessageBox, QPlainTextEdit, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout)

from ..services import backup, masters, trading
from ..services.common import BusinessError
from .enter_safe import EnterSafeDialog
from .imei_dialogs import ask_sale_imei
from .invoice_model import InvoiceDraft
from .parties import PartyForm
from .printing import print_invoice
from .widgets import money

COLS = ["ID", "Product", "Stock", "Qty", "Price", "Discount", "Amount", ""]
C_ID, C_NAME, C_STOCK, C_QTY, C_PRICE, C_DISC, C_AMT, C_DEL = range(8)
EDIT_ORDER = (C_QTY, C_PRICE, C_DISC)       # Enter walks through these cells


def _spin(maximum=1e9):
    s = QDoubleSpinBox()
    s.setRange(0, maximum)
    s.setDecimals(2)
    s.setGroupSeparatorShown(True)
    return s


_OPEN_NUMBERS = set()        # invoice numbers held by the invoice windows that are open right now


class SaleInvoiceDialog(EnterSafeDialog):
    def __init__(self, db, parent=None, invoice_id=None):
        super().__init__(parent)
        # minimize / maximize buttons next to the close button
        self.setWindowFlags(self.windowFlags() | Qt.WindowMinMaxButtonsHint | Qt.WindowCloseButtonHint)
        self.db = db
        self.inv_no = None
        self._force_close = False
        self.invoice_id = invoice_id          # set => editing a saved invoice
        self.draft = InvoiceDraft()
        self._loading = False
        self._paid_manual = False
        self.last_saved_id = None
        self._take_number()
        self._build()
        self._fit_window()
        self._load_customers()
        if invoice_id:
            self._load_existing(invoice_id)
        self._recalc()
        self.search.setFocus()

    # ---- invoice number: each open window keeps its own number ----
    def _take_number(self):
        if self.invoice_id:
            self.inv_no = self.db.scalar("SELECT no FROM invoices WHERE id=?", (self.invoice_id,), "")
            self.setWindowTitle(f"Edit Sale Invoice {self.inv_no}")
            return
        self.inv_no = trading.suggest_invoice_no(self.db, _OPEN_NUMBERS)
        _OPEN_NUMBERS.add(self.inv_no)
        self.setWindowTitle(f"Sale Invoice {self.inv_no}")

    def _release_number(self):
        _OPEN_NUMBERS.discard(self.inv_no)

    def reject(self):
        if self.draft.lines and not self._force_close:
            ask = QMessageBox.question(self, "Close invoice",
                                       f"Invoice {self.inv_no} is not saved. Close it without saving?",
                                       QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if ask != QMessageBox.Yes:
                return
        if not self.invoice_id:
            self._release_number()
        super().reject()

    def accept(self):
        if not self.invoice_id:
            self._release_number()
        super().accept()

    def _fit_window(self):
        """About 8 inch wide x 6 inch high (96 px per inch), and always inside the screen."""
        w, h = 8 * 96, 6 * 96
        screen = self.screen() or QApplication.primaryScreen()
        if screen:
            area = screen.availableGeometry()
            w, h = min(w, area.width() - 30), min(h, area.height() - 60)
        self.resize(w, h)

    # ================= layout =================
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(6)

        # ---- customer row ----
        row = QHBoxLayout()
        no_lbl = QLabel(f"Invoice No: <b>{self.inv_no}</b>")
        no_lbl.setStyleSheet("font-size: 14px; color: #1b6ef3; padding-right: 10px;")
        self.no_lbl = no_lbl
        row.addWidget(no_lbl)
        row.addWidget(QLabel("Customer:"))
        self.customer = QComboBox()
        self.customer.setEditable(True)
        self.customer.setMinimumWidth(240)
        self.customer.setInsertPolicy(QComboBox.NoInsert)
        row.addWidget(self.customer, 1)
        new_c = QPushButton("New Customer")
        new_c.setObjectName("secondary")
        new_c.clicked.connect(self._new_customer)
        row.addWidget(new_c)
        self.cust_info = QLabel()
        self.cust_info.setObjectName("subtitle")
        row.addWidget(self.cust_info)
        root.addLayout(row)

        # ---- product search ----
        self.search = QLineEdit(placeholderText="Search product: name, #tag, ID or similar spelling... "
                                                "(Enter = add)")
        self.search.textChanged.connect(self._search_products)
        self.search.returnPressed.connect(self._add_from_search)
        root.addWidget(self.search)
        self.results = QListWidget()
        self.results.setMaximumHeight(62)
        self.results.itemDoubleClicked.connect(lambda _: self._add_from_search())
        root.addWidget(self.results)

        # ---- lines ----
        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setMinimumHeight(110)
        head = self.table.horizontalHeader()
        head.setSectionResizeMode(QHeaderView.Fixed)
        head.setSectionResizeMode(C_NAME, QHeaderView.Stretch)       # product name takes the spare room
        for c, w in ((C_ID, 38), (C_STOCK, 56), (C_QTY, 56), (C_PRICE, 88), (C_DISC, 74), (C_AMT, 96), (C_DEL, 74)):
            self.table.setColumnWidth(c, w)
        self.table.itemChanged.connect(self._cell_changed)
        self.table.itemDelegate().closeEditor.connect(self._editor_closed)
        root.addWidget(self.table, 1)

        # ---- bottom: note + options (left), totals (right) ----
        bottom = QHBoxLayout()
        left = QVBoxLayout()
        left.setSpacing(3)
        left.addWidget(QLabel("Note (printed at the bottom of the bill):"))
        self.note = QPlainTextEdit()
        self.note.setMaximumHeight(44)
        left.addWidget(self.note)
        self.show_profit = QCheckBox("Show Profit / Loss")
        self.show_profit.toggled.connect(self._recalc)
        left.addWidget(self.show_profit)
        self.profit_lbl = QLabel()
        self.profit_lbl.setStyleSheet("font-size: 15px; font-weight: 700;")
        left.addWidget(self.profit_lbl)
        self.warn = QLabel()
        self.warn.setObjectName("error")
        self.warn.setWordWrap(True)
        left.addWidget(self.warn)
        left.addStretch()
        bottom.addLayout(left, 3)

        totals = QGridLayout()
        totals.setVerticalSpacing(3)
        self.subtotal_lbl = QLabel("0.00")
        self.disc = _spin()
        self.disc.valueChanged.connect(self._totals_edited)
        self.total_lbl = QLabel("0.00")
        self.total_lbl.setStyleSheet("font-size: 22px; font-weight: 800; color: #1b6ef3;")
        self.paid = _spin()
        self.paid.valueChanged.connect(self._paid_edited)
        self.balance_lbl = QLabel("0.00")
        self.balance_lbl.setStyleSheet("font-weight: 700; font-size: 14px;")
        for i, (text, w) in enumerate((("Sub Total", self.subtotal_lbl), ("Discount", self.disc),
                                       ("GRAND TOTAL", self.total_lbl), ("Paid now", self.paid),
                                       ("Balance (credit)", self.balance_lbl))):
            totals.addWidget(QLabel(text), i, 0)
            totals.addWidget(w, i, 1, Qt.AlignRight)
        bottom.addLayout(totals, 2)
        root.addLayout(bottom)

        # ---- buttons ----
        btns = QHBoxLayout()
        self.size = QComboBox()
        s = backup.get_settings(self.db.data_dir)
        self.size.addItem(f"Thermal ({int(s['thermal_width'])}mm)", "Thermal")
        self.size.addItem("A4", "A4")
        self.size.setCurrentIndex(1 if s.get("default_bill") == "a4" else 0)
        btns.addWidget(QLabel("Print size:"))
        btns.addWidget(self.size)
        btns.addStretch()
        close = QPushButton("Close")
        close.setObjectName("secondary")
        close.clicked.connect(self.reject)
        save = QPushButton("Save")
        save.clicked.connect(lambda: self._save(print_after=False))
        save_print = QPushButton("Save && Print (Ctrl+P)")
        save_print.clicked.connect(lambda: self._save(print_after=True))
        for b in (close, save, save_print):
            btns.addWidget(b)
        root.addLayout(btns)
        QShortcut(QKeySequence("Ctrl+P"), self, activated=lambda: self._save(print_after=True))
        QShortcut(QKeySequence("Ctrl+S"), self, activated=lambda: self._save(print_after=False))
        self.customer.currentIndexChanged.connect(self._customer_changed)

    # ================= customers =================
    def _load_customers(self, select_id=None):
        rows = masters.search_parties(self.db, "customer", "")
        rows.sort(key=lambda r: (not r["is_walkin"], r["name"].lower()))  # Walk-in first
        self.customer.blockSignals(True)
        self.customer.clear()
        for r in rows:
            label = r["name"] if r["is_walkin"] else f"{r['name']}  (ID {r['id']})"
            self.customer.addItem(label, r["id"])
        comp = QCompleter([self.customer.itemText(i) for i in range(self.customer.count())], self.customer)
        comp.setCaseSensitivity(Qt.CaseInsensitive)
        comp.setFilterMode(Qt.MatchContains)
        self.customer.setCompleter(comp)
        idx = self.customer.findData(select_id) if select_id else 0
        self.customer.setCurrentIndex(max(idx, 0))
        self.customer.blockSignals(False)
        self._customer_changed()

    def _party_id(self):
        pid = self.customer.currentData()
        if pid is None:  # typed text that matches an item
            i = self.customer.findText(self.customer.currentText(), Qt.MatchFixedString)
            pid = self.customer.itemData(i) if i >= 0 else None
        return pid

    def _is_walkin(self):
        pid = self._party_id()
        return bool(pid and self.db.scalar("SELECT is_walkin FROM parties WHERE id=?", (pid,)))

    def _customer_changed(self, *_):
        pid = self._party_id()
        if pid and not self._is_walkin():
            from ..services.common import customer_balance
            self.cust_info.setText(f"Previous balance: {money(customer_balance(self.db.conn, pid))}")
        else:
            self.cust_info.setText("Cash sale - full payment" if pid else "")
        self._recalc()

    def _new_customer(self):
        form = PartyForm(self.db, "customer", parent=self)
        if form.exec():
            self._load_customers(select_id=form.saved_id)

    # ================= products / lines =================
    def _search_products(self, text):
        self.results.clear()
        if not text.strip():
            return
        for p in masters.search_products(self.db, text, limit=30):
            self.results.addItem(f"{p['id']}  |  {p['name']}   (stock {p['stock']:g}, "
                                 f"price {money(p['sale_price'])})")
            self.results.item(self.results.count() - 1).setData(Qt.UserRole, p)
        if self.results.count():
            self.results.setCurrentRow(0)

    def _add_from_search(self):
        item = self.results.currentItem()
        if not item:
            return
        p = item.data(Qt.UserRole)
        serial = serial2 = None
        if p["track_serial"]:
            # The phone is NOT picked from the stock list: its IMEI must be typed again here.
            got = ask_sale_imei(self, p["name"], p["imei_mode"], checker=lambda a, b: self._check_unit(p, a, b))
            if got is None:
                return
            row = trading.check_sale_unit(self.db.conn, p, *got)          # use the numbers as stored
            serial, serial2 = row["serial"], row["imei2"]
        ln = self.draft.add_product(p, serial, serial2)
        idx = self.draft.lines.index(ln)
        self.search.clear()
        self.results.clear()
        self._refresh_table()
        QTimer.singleShot(0, lambda: self._edit_cell(idx, C_QTY))   # cursor goes to the quantity

    def _check_unit(self, p, i1, i2):
        used = self.draft.imeis_in_use()
        if i1 in used or (i2 and i2 in used):
            raise BusinessError("This phone is already on this invoice")
        trading.check_sale_unit(self.db.conn, p, i1, i2)   # must be in stock and match the stock record

    @staticmethod
    def _line_name(ln):
        if ln.get("serial2"):
            return f"{ln['name']}  [IMEI 1: {ln['serial']}  IMEI 2: {ln['serial2']}]"
        if ln.get("serial"):
            return f"{ln['name']}  [IMEI {ln['serial']}]"
        return ln["name"]

    def _refresh_table(self):
        self._loading = True
        self.table.setRowCount(len(self.draft.lines))
        for r, ln in enumerate(self.draft.lines):
            cells = [(C_ID, str(ln["product_id"]), False), (C_NAME, self._line_name(ln), False),
                     (C_STOCK, f"{ln['stock']:g}", False), (C_QTY, f"{ln['qty']:g}", not ln["track_serial"]),
                     (C_PRICE, f"{ln['price']:.2f}", True), (C_DISC, f"{ln['discount']:.2f}", True),
                     (C_AMT, money(InvoiceDraft.line_amount(ln)), False)]
            for col, text, editable in cells:
                it = QTableWidgetItem(text)
                flags = it.flags() | Qt.ItemIsEditable if editable else it.flags() & ~Qt.ItemIsEditable
                it.setFlags(flags)
                if col >= C_STOCK:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if col == C_QTY and ln["qty"] > ln["stock"]:
                    it.setBackground(QColor("#fdecea"))  # more than available stock
                self.table.setItem(r, col, it)
            rm = QPushButton("Remove")
            rm.setObjectName("secondary")
            rm.setAutoDefault(False)
            rm.clicked.connect(lambda _=False, i=r: self._remove_line(i))
            self.table.setCellWidget(r, C_DEL, rm)
        self._loading = False
        self._recalc()

    def _remove_line(self, i):
        if 0 <= i < len(self.draft.lines):
            del self.draft.lines[i]
            self._refresh_table()

    def _cell_changed(self, item):
        if self._loading:
            return
        r, c = item.row(), item.column()
        if c not in (C_QTY, C_PRICE, C_DISC) or r >= len(self.draft.lines):
            return
        try:
            v = float(item.text().replace(",", ""))
            if v < 0 or (c == C_QTY and v == 0):
                raise ValueError
            self.draft.lines[r][{C_QTY: "qty", C_PRICE: "price", C_DISC: "discount"}[c]] = v
        except ValueError:
            self.warn.setText("Enter a valid positive number.")
        # rebuild AFTER this edit has finished (rebuilding inside the edit signal can crash Qt)
        QTimer.singleShot(0, self._refresh_table)

    # ---- Enter key walks through the cells: Qty -> Price -> Discount -> back to the search box ----
    def _editor_closed(self, editor, hint):
        if hint == QAbstractItemDelegate.EndEditHint.SubmitModelCache:     # the user pressed Enter
            QTimer.singleShot(0, self._next_cell)

    def _next_cell(self):
        row, col = self.table.currentRow(), self.table.currentColumn()
        later = [c for c in EDIT_ORDER if c > col]
        if row >= 0 and later and self._edit_cell(row, later[0]):
            return
        self.search.setFocus()
        self.search.selectAll()

    def _edit_cell(self, row, col) -> bool:
        """Start editing the first editable cell at or after `col` in `row`."""
        for c in [x for x in EDIT_ORDER if x >= col]:
            it = self.table.item(row, c)
            if it is not None and it.flags() & Qt.ItemIsEditable:
                self.table.setFocus()
                self.table.setCurrentCell(row, c)
                self.table.editItem(it)
                return True
        return False

    # ================= totals =================
    def _totals_edited(self, *_):
        self.draft.discount = self.disc.value()
        self._recalc()

    def _paid_edited(self, *_):
        if not self._loading:
            self._paid_manual = True
        self._recalc()

    def _recalc(self, *_):
        d = self.draft
        d.discount = self.disc.value()
        total = d.total()
        self.subtotal_lbl.setText(money(d.subtotal()))
        self.total_lbl.setText(money(total))
        # Walk-in customers pay in full: paid follows the total until the user edits it.
        if self._is_walkin() and not self._paid_manual:
            self._loading = True
            self.paid.setValue(max(total, 0))
            self._loading = False
        self.balance_lbl.setText(money(total - self.paid.value()))
        profit = d.profit()
        self.profit_lbl.setVisible(self.show_profit.isChecked())
        self.profit_lbl.setText(("Profit: " if profit >= 0 else "Loss: ") + money(abs(profit)))
        self.profit_lbl.setStyleSheet("font-size: 15px; font-weight: 700; color: "
                                      + ("#12803c" if profit >= 0 else "#d92d20"))
        over = [ln for ln in d.over_stock() if not ln["track_serial"]]
        self.warn.setText("Not enough stock: " + ", ".join(f"{ln['name']} (have {ln['stock']:g})"
                                                          for ln in over) if over else "")

    # ================= save / edit =================
    def _load_existing(self, invoice_id):
        inv = self.db.one("SELECT * FROM invoices WHERE id=?", (invoice_id,))
        if not inv or inv["status"] == "cancelled":
            raise BusinessError("Invoice not found or cancelled")
        self.customer.setCurrentIndex(max(self.customer.findData(inv["party_id"]), 0))
        for it in self.db.query("SELECT * FROM invoice_items WHERE invoice_id=?", (invoice_id,)):
            p = self.db.one("SELECT p.*, p.opening_stock + COALESCE((SELECT SUM(qty) FROM stock_moves "
                            "WHERE product_id=p.id),0) AS stock FROM products p WHERE p.id=?", (it["product_id"],))
            p["stock"] += it["qty"]  # stock as it was before this invoice
            ln = self.draft.add_product(p, it["serial"], it["serial2"])
            ln.update(qty=it["qty"], price=it["price"], discount=it["discount"])
        self.disc.setValue(inv["discount"])
        self._paid_manual = True
        self.paid.setValue(inv["paid"])
        self.note.setPlainText(inv["note"] or "")
        self._refresh_table()

    def _save(self, print_after: bool):
        pid = self._party_id()
        if not pid:
            QMessageBox.warning(self, "Customer", "Please select a customer.")
            return
        try:
            args = dict(items=self.draft.service_items(), discount=self.disc.value(),
                        paid=self.paid.value(), note=self.note.toPlainText().strip())
            if self.invoice_id:
                trading.edit_invoice(self.db, self.invoice_id, pid, **args)
                saved = self.invoice_id
            else:
                saved = trading.create_invoice(self.db, pid, no=self.inv_no, **args)
        except BusinessError as exc:
            QMessageBox.warning(self, "Cannot save", str(exc))
            return
        self.last_saved_id = saved
        no = self.db.scalar("SELECT no FROM invoices WHERE id=?", (saved,), "")
        if print_after:
            try:
                print_invoice(self.db, saved, self.size.currentData())
            except Exception as exc:  # printing problems must never lose the saved invoice
                QMessageBox.warning(self, "Print", f"Invoice {no} was saved, but printing failed:\n{exc}")
        else:
            QMessageBox.information(self, "Saved", f"Invoice {no} saved.")
        if self.invoice_id:
            self.accept()
        else:
            self._reset_for_new()

    def _reset_for_new(self):
        self._release_number()                      # next bill of this window gets the next free number
        self._take_number()
        self.no_lbl.setText(f"Invoice No: <b>{self.inv_no}</b>")
        self.draft = InvoiceDraft()
        self._paid_manual = False
        self.disc.setValue(0)
        self.paid.setValue(0)
        self.note.clear()
        self.show_profit.setChecked(False)
        self._load_customers()
        self._refresh_table()
        self.search.setFocus()
