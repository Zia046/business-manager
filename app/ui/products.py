"""Products screen: search, add, edit, delete, low-stock highlight."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QComboBox, QDialog, QDoubleSpinBox, QSpinBox, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QPushButton, QVBoxLayout)

from ..services import masters
from ..services.common import BusinessError, is_owner
from .barcode_print import BarcodePrintDialog, ensure_barcode
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
        self.setMinimumWidth(480)
        p = product or {}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(26, 22, 26, 22)
        form = QFormLayout()
        form.addRow("ID", QLabel(str(p["id"]) if product else "Auto (system generated)"))
        self.name = QLineEdit(p.get("name", ""))

        # a category must always be chosen from the list (Utilities/New Account > Categories adds more)
        self.category = QComboBox()
        self.category.addItem("-- Select category --", None)
        for c in masters.list_categories(db):
            self.category.addItem(c["name"], c["is_mobile"])
        idx = self.category.findText(p.get("category") or "", Qt.MatchFixedString)
        self.category.setCurrentIndex(max(idx, 0))

        self.imei_mode = QComboBox()
        self.imei_mode.addItem("Single IMEI (one number)", "single")
        self.imei_mode.addItem("Double IMEI (two numbers)", "double")
        self.imei_mode.setCurrentIndex(1 if p.get("imei_mode") == "double" else 0)
        self.tags = QLineEdit(p.get("tags") or "", placeholderText="#mobile #samsung #android")
        self.unit = QLineEdit(p.get("unit") or "pcs")
        self.purchase = _spin(p.get("last_purchase_price", 0))
        self.sale = _spin(p.get("sale_price", 0))
        self.opening = _spin(p.get("opening_stock", 0), 3)
        self.low = _spin(p.get("low_stock_level", 0), 3)
        self.barcode = QLineEdit(p.get("barcode") or "", placeholderText="Scan, type, or press Generate Barcode")
        self.warranty = QSpinBox()
        self.warranty.setRange(0, 120)
        self.warranty.setSuffix(" month(s)")
        self.warranty.setSpecialValueText("No warranty")
        self.warranty.setValue(int(p.get("warranty_months") or 0))
        if product:  # cost and opening stock change only through purchases/sales
            self.purchase.setEnabled(False)
            self.opening.setEnabled(False)
        form.addRow("Name *", self.name)
        form.addRow("Category *", self.category)
        form.addRow("IMEI type", self.imei_mode)
        form.addRow("Hash tags", self.tags)
        form.addRow("Unit", self.unit)
        if is_owner():
            form.addRow("Purchase Price", self.purchase)
        form.addRow("Sale Price", self.sale)
        form.addRow("Opening Stock", self.opening)
        form.addRow("Low-stock alert at", self.low)
        form.addRow("Warranty on sale", self.warranty)
        gen = QPushButton("Generate Barcode")
        gen.setObjectName("secondary")
        gen.setAutoDefault(False)
        gen.setToolTip("Makes a new random number (8 digits) that no other product has")
        gen.clicked.connect(self._generate_barcode)
        brow = QHBoxLayout()
        brow.addWidget(self.barcode, 1)
        brow.addWidget(gen)
        form.addRow("Barcode", brow)
        lay.addLayout(form)
        self.hint = QLabel("")
        self.hint.setObjectName("subtitle")
        self.hint.setWordWrap(True)
        lay.addWidget(self.hint)
        self.error = QLabel("")
        self.error.setObjectName("error")
        self.error.setWordWrap(True)
        lay.addWidget(self.error)
        save = QPushButton("Save")
        save.setDefault(True)
        save.clicked.connect(self.save)
        lay.addWidget(save)
        self.category.currentIndexChanged.connect(self._category_changed)
        self._category_changed()
        if product and masters.db_has_imei(db, product["id"]):
            self.imei_mode.setEnabled(False)       # cannot switch single/double once IMEI numbers exist

    def _is_mobile(self) -> bool:
        return self.category.currentData() == 1

    def _category_changed(self, *_):
        mobile = self._is_mobile()
        self.imei_mode.setEnabled(mobile)
        if mobile:
            self.opening.setValue(0)
            self.opening.setEnabled(False)
            self.hint.setText("Mobile phones are added through Stock Purchase, where the IMEI number of "
                              "every phone must be entered (10 to 100 digits). Choose single or double IMEI.")
        else:
            self.opening.setEnabled(self.product is None)
            self.hint.setText("")

    def _generate_barcode(self):
        if self.barcode.text().strip() and QMessageBox.question(
                self, "Barcode", "This product already has a barcode. Replace it with a new one?\n"
                "(Labels already printed with the old barcode will no longer match.)") != QMessageBox.Yes:
            return
        try:
            self.barcode.setText(masters.generate_barcode(self.db))
        except BusinessError as exc:
            self.error.setText(str(exc))

    def save(self):
        try:
            cat = self.category.currentText() if self.category.currentData() is not None else ""
            mode = self.imei_mode.currentData()
            if self.product:
                masters.update_product(self.db, self.product["id"], name=self.name.text().strip(),
                                       category=cat, tags=self.tags.text(), unit=self.unit.text(),
                                       sale_price=self.sale.value(), low_stock_level=self.low.value(),
                                       imei_mode=mode, warranty_months=self.warranty.value(),
                                       barcode=self.barcode.text())
                self.saved_id = self.product["id"]
            else:
                self.saved_id = masters.add_product(
                    self.db, self.name.text(), self.sale.value(), self.purchase.value(),
                    self.opening.value(), cat, self.tags.text(), self.unit.text(),
                    self.low.value(), imei_mode=mode,
                    warranty_months=self.warranty.value(), barcode=self.barcode.text())
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
        self.search = QLineEdit(placeholderText="Search by name, #tag, ID, similar spelling - or scan a barcode...")
        self.search.textChanged.connect(self.reload)
        top.addWidget(self.search)
        for text, fn, name in (("Add New", self.add, None), ("Edit", self.edit, "secondary"),
                               ("Print Barcode", self.print_barcode, "secondary"),
                               ("Delete", self.delete, "secondary")):
            b = QPushButton(text)
            if name:
                b.setObjectName(name)
            b.clicked.connect(fn)
            top.addWidget(b)
        lay.addLayout(top)
        self.table = make_table(["ID", "Name", "Category", "Tags", "Unit", "Avg Cost", "Sale Price", "Stock"])
        self.table.doubleClicked.connect(self.edit)
        if not is_owner():
            self.table.setColumnHidden(5, True)          # Avg Cost is hidden from staff
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
                    (5, 6, 7), QColor("#FEE2E2") if is_low else None)
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

    def print_barcode(self):
        p = self._selected()
        if not p:
            return
        p = ensure_barcode(self.db, p, self)
        if p:
            BarcodePrintDialog(self.db, p, self).exec()
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
