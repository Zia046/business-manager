"""Print the barcode of one product: on a barcode (label) printer, or on A4 pages."""
import math

from PySide6.QtWidgets import (QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel, QMessageBox, QPushButton,
                               QSpinBox, QVBoxLayout)

from ..services import masters
from ..services.common import BusinessError
from .printing import print_labels


def ensure_barcode(db, product, parent=None):
    """A product needs its own barcode before printing; offer to generate one. Returns the product or None."""
    if product.get("barcode"):
        return product
    if QMessageBox.question(parent, "Barcode", f"'{product['name']}' has no barcode yet.\n\n"
                            "Generate a new barcode for it now?") != QMessageBox.Yes:
        return None
    try:
        masters.update_product(db, product["id"], barcode=masters.generate_barcode(db))
    except BusinessError as exc:
        QMessageBox.warning(parent, "Barcode", str(exc))
        return None
    return db.one("SELECT * FROM products WHERE id=?", (product["id"],))


class BarcodePrintDialog(QDialog):
    def __init__(self, db, product, parent=None):
        super().__init__(parent)
        self.db, self.product = db, product
        self.setWindowTitle("Print Barcode")
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.addWidget(QLabel(f"<b style='font-size:15px'>{product['name']}</b><br>"
                             f"Barcode: <b>{masters.barcode_for(product)}</b>"))
        form = QFormLayout()
        self.kind = QComboBox()
        self.kind.addItem("Barcode printer (one label after another)", "roll")
        self.kind.addItem("A4 page", "grid")
        self.kind.currentIndexChanged.connect(self._changed)
        self.count = QSpinBox()
        self.count.setRange(1, 5000)
        self.count.setValue(1)
        self.per_page = QSpinBox()
        self.per_page.setRange(1, 84)
        self.per_page.setValue(21)
        self.pages = QSpinBox()
        self.pages.setRange(1, 60)
        self.pages.setValue(1)
        self.count_row_label = QLabel("How many barcodes")
        form.addRow("Print on", self.kind)
        form.addRow(self.count_row_label, self.count)
        self.pp_label, self.pg_label = QLabel("Barcodes on one A4 page"), QLabel("Number of A4 pages")
        form.addRow(self.pp_label, self.per_page)
        form.addRow(self.pg_label, self.pages)
        lay.addLayout(form)
        self.info = QLabel("")
        self.info.setObjectName("subtitle")
        self.info.setWordWrap(True)
        lay.addWidget(self.info)
        for w in (self.count, self.per_page, self.pages):
            w.valueChanged.connect(self._changed)
        row = QHBoxLayout()
        go = QPushButton("Print")
        go.clicked.connect(self._print)
        cancel = QPushButton("Cancel")
        cancel.setObjectName("secondary")
        cancel.clicked.connect(self.reject)
        row.addWidget(go)
        row.addWidget(cancel)
        lay.addLayout(row)
        self._changed()

    def _a4(self):
        return self.kind.currentData() == "grid"

    def _changed(self, *_):
        a4 = self._a4()
        for w in (self.pp_label, self.per_page, self.pg_label, self.pages):
            w.setVisible(a4)
        for w in (self.count_row_label, self.count):
            w.setVisible(not a4)
        if a4:
            from ..reports.labels_pdf import grid_layout
            cols, rows, w, h = grid_layout(self.per_page.value())
            self.info.setText(f"Each page: {cols} column(s) x {rows} row(s) = {cols * rows} places for "
                              f"{self.per_page.value()} barcode(s).  Total: {self.per_page.value() * self.pages.value()} "
                              f"barcode(s) on {self.pages.value()} page(s).")
        else:
            self.info.setText("Sent to the label printer chosen in Printer Settings.")

    def totals(self):
        """(copies, per_page) to print."""
        if self._a4():
            return self.per_page.value() * self.pages.value(), self.per_page.value()
        return self.count.value(), None

    def _print(self):
        copies, per_page = self.totals()
        try:
            print_labels(self.db, [(self.product["id"], copies)], self.kind.currentData(), per_page)
        except Exception as exc:
            QMessageBox.warning(self, "Print Barcode", f"Could not print:\n{exc}")
            return
        self.accept()
