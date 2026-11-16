"""Phones in Stock: every phone that is in the shop now, one line per IMEI, with search, filters and sorting."""
from PySide6.QtWidgets import QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout

from ..services import phones
from ..services.common import is_owner
from .widgets import make_table, money, set_row

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
        self.headers = ["Brand", "Model", "Type", "RAM", "Storage", "Condition", "IMEI 1", "IMEI 2"] + (
            ["Purchase Price"] if self.owner else []) + ["Selling Price", "Status"]
        self.table = make_table(self.headers, stretch_col=1)
        lay.addWidget(self.table, 1)
        bottom = QHBoxLayout()
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
