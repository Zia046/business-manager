"""Phones in Stock: every phone that is in the shop now, one line per IMEI, with search, filters and sorting."""
from PySide6.QtWidgets import (QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QHBoxLayout, QInputDialog, QLabel,
                               QLineEdit, QMessageBox, QPushButton, QVBoxLayout)

from ..config import APP_NAME
from ..services import phones
from ..services.common import BusinessError, is_owner
from .enter_safe import EnterSafeDialog
from .phone_fields import PhoneFields
from .widgets import make_table, money, set_row


def _money_box(value):
    box = QDoubleSpinBox()
    box.setRange(0, 1e9)
    box.setDecimals(2)
    box.setGroupSeparatorShown(True)
    box.setValue(float(value or 0))
    return box


class PhoneEditDialog(EnterSafeDialog):
    """Correct one phone of the stock. Saved invoices and purchases keep their own prices and IMEIs."""

    def __init__(self, db, row, parent=None):
        super().__init__(parent)
        self.db, self.row = db, row
        self.setWindowTitle("Edit Phone")
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 18, 24, 18)
        form = QFormLayout()
        self.brand = QLineEdit(row["brand"] or "", placeholderText="e.g. Infinix, Samsung, Nokia")
        self.name = QLineEdit(row["name"])
        form.addRow("Brand", self.brand)
        form.addRow("Model *", self.name)
        self.spec = PhoneFields(form, row["mobile_type"], row["ram_gb"], row["storage_gb"],
                                allow_unknown=not row["mobile_type"])
        self.condition = QComboBox()
        for key, label in phones.CONDITIONS.items():
            self.condition.addItem(label, key)
        self.condition.setCurrentIndex(max(self.condition.findData(row["condition"]), 0))
        form.addRow("Condition", self.condition)
        self.imei1 = QLineEdit(row["imei1"])
        self.imei2 = QLineEdit(row["imei2"] or "", placeholderText="Leave empty if the phone has one IMEI")
        form.addRow("IMEI 1 *", self.imei1)
        form.addRow("IMEI 2", self.imei2)
        self.rate = _money_box(row["purchase_price"])
        self.sale = _money_box(row["sale_price"])
        form.addRow("Purchase Rate", self.rate)
        form.addRow("Selling Price", self.sale)
        lay.addLayout(form)
        note = QLabel("Saved invoices and purchases are not changed. The new purchase rate is used for this phone's "
                      "stock value and the profit when it is sold.")
        note.setObjectName("subtitle")
        note.setWordWrap(True)
        lay.addWidget(note)
        self.error = QLabel("")
        self.error.setObjectName("error")
        self.error.setWordWrap(True)
        lay.addWidget(self.error)
        row_ = QHBoxLayout()
        row_.addStretch()
        cancel = QPushButton("Cancel")
        cancel.setObjectName("secondary")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Save Changes")
        save.clicked.connect(self.save)
        row_.addWidget(cancel)
        row_.addWidget(save)
        lay.addLayout(row_)

    def save(self):
        try:
            phones.edit_phone(self.db, self.row["serial_id"], self.name.text(), self.imei1.text(), self.rate.value(),
                              self.sale.value(), imei2=self.imei2.text(), brand=self.brand.text(),
                              condition=self.condition.currentData(), **self.spec.values())
        except BusinessError as exc:
            self.error.setText(str(exc))
            return
        self.accept()

SORTS = [("Model (A-Z)", "model", False), ("Purchase price: low to high", "purchase", False),
         ("Purchase price: high to low", "purchase", True), ("Selling price: low to high", "sale", False),
         ("Selling price: high to low", "sale", True), ("RAM: high to low", "ram", True),
         ("Storage: high to low", "storage", True)]


class PhoneStockWindow(QDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.owner = is_owner()                 # staff do not see purchase prices
        self.setWindowTitle("Phones in Stock")
        self.resize(1180, 640)
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.search = QLineEdit(placeholderText="Search brand, model or IMEI...")
        self.search.setClearButtonEnabled(True)
        top.addWidget(self.search, 2)
        self.condition = self._combo([("All conditions", ""), ("New", "new"), ("Used", "used")])
        self.kind = self._combo([("All types", "")] + [(v, k) for k, v in phones.TYPES.items()])
        vals = phones.filter_values(db)
        self.ram = self._combo([("Any RAM", None)] + [(f"{n} GB RAM", n) for n in vals["ram"]])
        self.storage = self._combo([("Any storage", None)] + [(f"{n} GB storage", n) for n in vals["storage"]])
        self.sort = self._combo([(label, i) for i, (label, _, _) in enumerate(SORTS)])
        if not self.owner:                      # no purchase-price sorting for staff
            for i in (2, 1):
                self.sort.removeItem(i)
        for w in (self.condition, self.kind, self.ram, self.storage, self.sort):
            top.addWidget(w)
        lay.addLayout(top)
        self.rows = []
        self.headers = ["Brand", "Model", "Type", "RAM", "Storage", "Condition", "IMEI 1", "IMEI 2"] + (
            ["Purchase Price"] if self.owner else []) + ["Selling Price", "Status"]
        self.table = make_table(self.headers, stretch_col=1)
        lay.addWidget(self.table, 1)
        bottom = QHBoxLayout()
        if self.owner:                          # only the owner may correct or remove a phone
            self.table.doubleClicked.connect(self.edit)
            for text, fn, secondary in (("Edit", self.edit, False), ("Delete", self.delete, True)):
                b = QPushButton(text)
                b.setAutoDefault(False)
                if secondary:
                    b.setObjectName("secondary")
                b.clicked.connect(fn)
                bottom.addWidget(b)
        self.total = QLabel("")
        self.total.setStyleSheet("font-weight: 700;")
        close = QPushButton("Close")
        close.setObjectName("secondary")
        close.clicked.connect(self.reject)
        bottom.addWidget(self.total, 1)
        bottom.addWidget(close)
        lay.addLayout(bottom)
        self.search.textChanged.connect(self.reload)
        self.reload()

    def _combo(self, items):
        box = QComboBox()
        for label, data in items:
            box.addItem(label, data)
        box.currentIndexChanged.connect(lambda *_: self.reload())
        return box

    def reload(self, *_):
        if not hasattr(self, "table"):
            return
        _, key, desc = SORTS[self.sort.currentData()]
        rows = phones.in_stock(self.db, self.search.text(), self.condition.currentData(), self.kind.currentData(),
                               self.ram.currentData(), self.storage.currentData(), key, desc)
        self.rows = rows
        self.table.setRowCount(len(rows))
        money_cols = (8, 9) if self.owner else (8,)
        for i, r in enumerate(rows):
            keypad = r["mobile_type"] == "keypad"
            values = [r["brand"], r["name"], phones.TYPES.get(r["mobile_type"], "-"),
                      "Not required" if keypad else phones.gb(r["ram_gb"]),
                      "Not required" if keypad else phones.gb(r["storage_gb"]),
                      phones.CONDITIONS[r["condition"]], r["imei1"], r["imei2"] or ""]
            if self.owner:
                values.append(money(r["purchase_price"]))
            values += [money(r["sale_price"]) if r["sale_price"] else "-", r["status"]]
            set_row(self.table, i, values, money_cols)
        text = f"{len(rows)} phone(s) available"
        if self.owner:
            text += f"   |   purchase value {money(sum(r['purchase_price'] for r in rows))}"
        self.total.setText(text + f"   |   selling value {money(sum(r['sale_price'] for r in rows))}")

    def _selected(self):
        sel = self.table.selectionModel().selectedRows()
        if not sel:
            QMessageBox.information(self, APP_NAME, "Select a phone first.")
            return None
        return self.rows[sel[0].row()]

    def edit(self, *_):
        row = self._selected()
        if row and PhoneEditDialog(self.db, row, self).exec():
            self.reload()
            self._refresh_home()

    def delete(self):
        row = self._selected()
        if not row:
            return
        text = (f"Remove this phone from the stock?\n\n{row['brand']} {row['name']}\nIMEI {row['imei1']}"
                + (f" / {row['imei2']}" if row["imei2"] else "") + f"\nPurchase rate {money(row['purchase_price'])}"
                "\n\nUse this for a phone entered by mistake, lost or damaged. If it goes back to the supplier, "
                "use Purchase Return instead (that also settles the money).")
        if QMessageBox.question(self, "Delete Phone", text, QMessageBox.Yes | QMessageBox.No,
                                QMessageBox.No) != QMessageBox.Yes:
            return
        reason, ok = QInputDialog.getText(self, "Delete Phone", "Why is this phone removed? (required)")
        if not ok:
            return
        try:
            phones.remove_phone(self.db, row["serial_id"], reason)
        except BusinessError as exc:
            QMessageBox.warning(self, "Delete Phone", str(exc))
            return
        self.reload()
        self._refresh_home()

    def _refresh_home(self):
        win = self.parent()
        while win is not None and not hasattr(win, "refresh_dashboard"):
            win = win.parent()
        if win is not None:
            try:
                win.refresh_dashboard()
            except Exception:
                pass
