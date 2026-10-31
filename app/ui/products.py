"""Products screen: search, add, edit, delete, low-stock highlight."""
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QDialog, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QPushButton, QVBoxLayout)

from ..services import masters
from ..services.common import BusinessError
from .widgets import make_table, money, selected_id, set_row


def _spin(value=0.0, decimals=2):
    s = QDoubleSpinBox()
    s.setRange(0, 1e9)
    s.setDecimals(decimals)
    s.setValue(value)
    return s


class ProductForm(QDialog):
    def __init__(self, db, product=None, parent=None):
        super().__init__(parent)
        self.db, self.product = db, product
        self.saved_id = None
        self.setWindowTitle("Edit Product" if product else "New Product")
        self.setMinimumWidth(460)
        p = product or {}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(26, 22, 26, 22)
        form = QFormLayout()
        form.addRow("ID", QLabel(str(p["id"]) if product else "Auto (system generated)"))
        self.name = QLineEdit(p.get("name", ""))
        self.category = QLineEdit(p.get("category") or "")
        self.tags = QLineEdit(p.get("tags") or "", placeholderText="#mobile #samsung #android")
        self.unit = QLineEdit(p.get("unit") or "pcs")
        self.purchase = _spin(p.get("last_purchase_price", 0))
        self.sale = _spin(p.get("sale_price", 0))
        self.opening = _spin(p.get("opening_stock", 0), 3)
        self.low = _spin(p.get("low_stock_level", 0), 3)
        self.serial = QCheckBox("Track IMEI / serial number for each piece")
        self.serial.setChecked(bool(p.get("track_serial")))
        if product:  # cost and opening stock change only through purchases/sales
            self.purchase.setEnabled(False)
            self.opening.setEnabled(False)
        form.addRow("Name *", self.name)
        form.addRow("Category", self.category)
        form.addRow("Hash tags", self.tags)
        form.addRow("Unit", self.unit)
        form.addRow("Purchase Price", self.purchase)
        form.addRow("Sale Price", self.sale)
        form.addRow("Opening Stock", self.opening)
        form.addRow("Low-stock alert at", self.low)
        form.addRow("", self.serial)
        lay.addLayout(form)
        self.error = QLabel("")
        self.error.setObjectName("error")
        lay.addWidget(self.error)
        save = QPushButton("Save")
        save.setDefault(True)
        save.clicked.connect(self.save)
        lay.addWidget(save)

    def save(self):
        try:
            if self.product:
                masters.update_product(self.db, self.product["id"], name=self.name.text().strip(),
                                       category=self.category.text(), tags=self.tags.text(),
                                       unit=self.unit.text(), sale_price=self.sale.value(),
                                       low_stock_level=self.low.value(),
                                       track_serial=int(self.serial.isChecked()))
                self.saved_id = self.product["id"]
            else:
                self.saved_id = masters.add_product(
                    self.db, self.name.text(), self.sale.value(), self.purchase.value(),
                    self.opening.value(), self.category.text(), self.tags.text(), self.unit.text(),
                    self.low.value(), self.serial.isChecked())
        except BusinessError as exc:
            self.error.setText(str(exc))
            return
        self.accept()


class ProductsWindow(QDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Products")
        self.resize(1000, 600)
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.search = QLineEdit(placeholderText="Search by name, #tag, ID or similar spelling...")
        self.search.textChanged.connect(self.reload)
        top.addWidget(self.search)
        for text, fn, name in (("Add New", self.add, None), ("Edit", self.edit, "secondary"),
                               ("Delete", self.delete, "secondary")):
            b = QPushButton(text)
            if name:
                b.setObjectName(name)
            b.clicked.connect(fn)
            top.addWidget(b)
        lay.addLayout(top)
        self.table = make_table(["ID", "Name", "Category", "Tags", "Unit", "Avg Cost", "Sale Price", "Stock"])
        self.table.doubleClicked.connect(self.edit)
        lay.addWidget(self.table)
        self.info = QLabel()
        lay.addWidget(self.info)
        self.reload()

    def reload(self):
        rows = masters.search_products(self.db, self.search.text(), limit=500)
        self.table.setRowCount(len(rows))
        low = 0
        for i, r in enumerate(rows):
            is_low = r["stock"] <= r["low_stock_level"]
            low += is_low
            set_row(self.table, i, [r["id"], r["name"], r["category"], r["tags"], r["unit"],
                                    money(r["avg_cost"]), money(r["sale_price"]), f"{r['stock']:g}"],
                    (5, 6, 7), QColor("#fdecea") if is_low else None)
        self.info.setText(f"{len(rows)} products     Low stock (red): {low}")

    def add(self):
        if ProductForm(self.db, parent=self).exec():
            self.reload()

    def _selected(self):
        pid = selected_id(self.table)
        if pid is None:
            QMessageBox.information(self, "Select", "Please select a row first.")
            return None
        return self.db.one("SELECT * FROM products WHERE id=?", (pid,))

    def edit(self, *_):
        p = self._selected()
        if p and ProductForm(self.db, p, self).exec():
            self.reload()

    def delete(self):
        p = self._selected()
        if not p:
            return
        if QMessageBox.question(self, "Delete", f"Delete '{p['name']}'?\n"
                                "(If it has stock history it will only be hidden.)") != QMessageBox.Yes:
            return
        if masters.delete_product(self.db, p["id"]) == "deactivated":
            QMessageBox.information(self, "Done", "Product has history, so it was hidden "
                                    "instead of deleted.")
        self.reload()
