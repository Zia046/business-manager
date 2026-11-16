"""Purchase 2nd Hand Phone: the entry form, and the purchase history with the details of each phone."""
from PySide6.QtCore import QDate
from PySide6.QtWidgets import (QDateEdit, QDialog, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPushButton, QVBoxLayout)

from ..config import APP_NAME
from ..services import phones, used_phones
from ..services.common import BusinessError
from .enter_safe import EnterSafeDialog
from .payments_ui import _stamp
from .phone_fields import PhoneFields
from .theme import C_GREEN, C_RED, NAVY
from .widgets import make_table, money, set_row


def _head(text):
    lab = QLabel(text)
    lab.setStyleSheet(f"font-size: 15px; font-weight: 800; color: {NAVY}; padding: 6px 0 2px 8px; "
                      f"border-left: 4px solid {C_RED};")
    return lab


def _amount_box():
    box = QDoubleSpinBox()
    box.setRange(0, 1e9)
    box.setDecimals(2)
    box.setGroupSeparatorShown(True)
    return box


class UsedPhoneDialog(EnterSafeDialog):
    """One second-hand phone bought from a person for cash."""

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Purchase 2nd Hand Phone")
        self.setMinimumWidth(560)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(26, 20, 26, 20)
        lay.setSpacing(8)

        lay.addWidget(_head("Customer / Seller Information"))
        f1 = QFormLayout()
        self.seller = QLineEdit()
        self.cnic = QLineEdit(placeholderText="13 digits, e.g. 15101-1234567-1")
        self.address = QLineEdit()
        self.phone = QLineEdit(placeholderText="e.g. 03xx-xxxxxxx")
        f1.addRow("Customer Name *", self.seller)
        f1.addRow("CNIC Number", self.cnic)
        f1.addRow("Address", self.address)
        f1.addRow("Mobile Number", self.phone)
        lay.addLayout(f1)

        lay.addWidget(_head("Mobile Phone Information"))
        f2 = QFormLayout()
        self.model = QLineEdit(placeholderText="e.g. Infinix Hot 40")
        self.model_no = QLineEdit(placeholderText="e.g. X6836")
        self.imei1 = QLineEdit(placeholderText="Compulsory - type or scan")
        self.imei2 = QLineEdit(placeholderText="Optional - leave empty if the phone has one IMEI")
        f2.addRow("Purchased Mobile Model *", self.model)
        f2.addRow("Model Number", self.model_no)
        self.spec = PhoneFields(f2)                 # Mobile Type, RAM (GB), Storage (GB)
        f2.addRow("IMEI Number 1 *", self.imei1)
        f2.addRow("IMEI Number 2", self.imei2)
        lay.addLayout(f2)

        lay.addWidget(_head("Purchase Information"))
        f3 = QFormLayout()
        self.price = _amount_box()
        self.sale_price = _amount_box()
        self.date = QDateEdit(QDate.currentDate())
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("dd-MM-yyyy")
        self.margin = QLabel("")
        self.margin.setObjectName("subtitle")
        f3.addRow("Purchase Price (cash paid) *", self.price)
        f3.addRow("Sale Price", self.sale_price)
        f3.addRow("", self.margin)
        f3.addRow("Purchase Date", self.date)
        lay.addLayout(f3)
        self.price.valueChanged.connect(self._show_margin)
        self.sale_price.valueChanged.connect(self._show_margin)

        self.error = QLabel("")
        self.error.setObjectName("error")
        self.error.setWordWrap(True)
        lay.addWidget(self.error)
        row = QHBoxLayout()
        hist = QPushButton("Purchase History")
        hist.setObjectName("secondary")
        hist.clicked.connect(lambda: UsedPhoneHistory(self.db, self).exec())
        close = QPushButton("Close")
        close.setObjectName("secondary")
        close.clicked.connect(self.reject)
        save = QPushButton("Save Purchase")
        save.clicked.connect(self.save)
        row.addWidget(hist)
        row.addStretch()
        row.addWidget(close)
        row.addWidget(save)
        lay.addLayout(row)

    def _show_margin(self, *_):
        buy, sell = self.price.value(), self.sale_price.value()
        if buy > 0 and sell > 0:
            diff = sell - buy
            self.margin.setText(f"Expected {'profit' if diff >= 0 else 'LOSS'}: {money(abs(diff))}")
            self.margin.setStyleSheet(f"color: {C_GREEN if diff >= 0 else C_RED}; font-weight: 700;")
        else:
            self.margin.setText("")

    def save(self):
        self.error.setText("")
        try:
            rid = used_phones.purchase(
                self.db, self.seller.text(), self.model.text(), self.imei1.text(), self.price.value(),
                cnic=self.cnic.text(), address=self.address.text(), phone=self.phone.text(),
                model_no=self.model_no.text(), imei2=self.imei2.text(), sale_price=self.sale_price.value(),
                date=_stamp(self.date.date()), **self.spec.values())
        except BusinessError as exc:
            self.error.setText(str(exc))
            return
        r = used_phones.detail(self.db, rid)
        QMessageBox.information(
            self, APP_NAME,
            f"Saved ({r['no']}).\n\nThe phone is now in Phones in Stock as:\n{r['product_name']}\n\n"
            "Sell it on the normal Sale Invoice by typing its name or IMEI.")
        for w in (self.seller, self.cnic, self.address, self.phone, self.model, self.model_no, self.imei1, self.imei2):
            w.clear()
        self.price.setValue(0)
        self.sale_price.setValue(0)
        self.spec.ram.setValue(0)
        self.spec.storage.setValue(0)
        self.seller.setFocus()


def detail_text(r) -> str:
    lines = [("Record No", r["no"]), ("Purchase Date", r["date"][:16]), ("", ""),
             ("Seller Name", r["seller_name"]), ("CNIC", r["cnic"] or "-"), ("Mobile", r["phone"] or "-"),
             ("Address", r["address"] or "-"), ("", ""),
             ("Phone Model", r["model"]), ("Model Number", r["model_no"] or "-"),
             ("Mobile Type", phones.TYPES.get(r.get("mobile_type"), "-")),
             ("RAM", "Not required" if r.get("mobile_type") == "keypad" else phones.gb(r.get("ram_gb"))),
             ("Storage", "Not required" if r.get("mobile_type") == "keypad" else phones.gb(r.get("storage_gb"))),
             ("IMEI 1", r["imei1"]),
             ("IMEI 2", r["imei2"] or "-"), ("In stock as", r["product_name"] or "-"), ("", ""),
             ("Purchase Price", money(r["price"])), ("Sale Price", money(r["sale_price"]) if r["sale_price"] else "-"),
             ("Status", r["status"])]
    if r["stock_status"] == "sold":
        lines += [("Sold on", f"{(r['sold_date'] or '')[:10]}  ({r['invoice_no']})"),
                  ("Sold for", money(r["sold_price"] or 0)),
                  ("Profit / Loss", money(r["profit"]) if r["profit"] is not None else "-")]
    return "<table cellspacing='4'>" + "".join(
        f"<tr><td><b>{k}</b></td><td>&nbsp;&nbsp;{v}</td></tr>" if k else "<tr><td colspan='2'>&nbsp;</td></tr>"
        for k, v in lines) + "</table>"


class UsedPhoneHistory(QDialog):
    HEADERS = ["No", "Purchase Date", "Seller Name", "Phone Model", "Model Number", "RAM / Storage", "IMEI 1",
               "IMEI 2", "Purchase Price", "Sale Price", "Status"]

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db, self.rows = db, []
        self.setWindowTitle("2nd Hand Phone Purchase History")
        self.resize(1080, 620)
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.search = QLineEdit(placeholderText="Search seller, model, IMEI, CNIC or mobile...")
        self.search.textChanged.connect(self.reload)
        top.addWidget(self.search, 1)
        new = QPushButton("New Purchase")
        new.clicked.connect(self._new)
        view = QPushButton("View Details")
        view.setObjectName("secondary")
        view.clicked.connect(self._view)
        top.addWidget(view)
        top.addWidget(new)
        lay.addLayout(top)
        self.table = make_table(self.HEADERS, stretch_col=2)
        self.table.doubleClicked.connect(self._view)
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
        self.reload()

    def reload(self, *_):
        self.rows = used_phones.history(self.db, self.search.text())
        self.table.setRowCount(len(self.rows))
        for i, r in enumerate(self.rows):
            set_row(self.table, i, [r["no"], r["date"][:10], r["seller_name"], r["model"], r["model_no"] or "",
                                    phones.spec(r), r["imei1"], r["imei2"] or "", money(r["price"]),
                                    money(r["sale_price"]) if r["sale_price"] else "", r["status"]], (8, 9))
        in_stock = sum(1 for r in self.rows if r["stock_status"] == "in_stock")
        self.total.setText(f"{len(self.rows)} phone(s) bought   |   total paid {money(sum(r['price'] for r in self.rows))}"
                           f"   |   {in_stock} still in stock")

    def _view(self, *_):
        sel = self.table.selectionModel().selectedRows()
        if not sel:
            QMessageBox.information(self, APP_NAME, "Select a row first.")
            return
        box = QMessageBox(self)
        box.setWindowTitle("2nd Hand Phone - Purchase Details")
        box.setText(detail_text(self.rows[sel[0].row()]))
        box.exec()

    def _new(self):
        if isinstance(self.parent(), UsedPhoneDialog):       # opened from the form: go back to it
            self.accept()
            return
        UsedPhoneDialog(self.db, self).exec()
        self.reload()
