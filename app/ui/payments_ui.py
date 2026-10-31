"""Payments / Receipts windows: cash received, payment to supplier, refund to customer, expenses."""
from PySide6.QtCore import QDate, QDateTime
from PySide6.QtWidgets import (QComboBox, QDateEdit, QDialog, QDoubleSpinBox, QFormLayout, QHBoxLayout,
                               QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout)

from ..services import payments
from ..services.common import BusinessError, customer_balance, supplier_balance
from .party_picker import combo_party_id, make_party_combo
from .printing import print_voucher
from .widgets import money

EXPENSE_CATEGORIES = ["Rent", "Electricity", "Salary", "Transport", "Tea / Food", "Repair", "Internet / Phone",
                      "Other"]

MODES = {
    "receive": dict(title="Cash Received from Customer", kind="customer", party_label="Customer",
                    action=payments.receive_from_customer, hint="Customer's outstanding balance:"),
    "pay_supplier": dict(title="Payment to Supplier", kind="supplier", party_label="Supplier",
                         action=payments.pay_supplier, hint="We owe the supplier:"),
    "pay_customer": dict(title="Payment to Customer (refund)", kind="customer", party_label="Customer",
                         action=payments.pay_customer, hint="Customer's current balance:"),
    "expense": dict(title="Expenses", kind=None),
}


def _stamp(qdate: QDate) -> str:
    """Selected day + current time, in the database's date format."""
    return f"{qdate.toString('yyyy-MM-dd')} {QDateTime.currentDateTime().toString('HH:mm:ss')}"


class PaymentDialog(QDialog):
    def __init__(self, db, mode, parent=None):
        super().__init__(parent)
        self.db, self.mode, self.cfg = db, mode, MODES[mode]
        self.setWindowTitle(self.cfg["title"])
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 24)
        form = QFormLayout()
        if mode == "expense":
            self.category = QComboBox()
            self.category.setEditable(True)
            self.category.addItems(EXPENSE_CATEGORIES)
            form.addRow("Category *", self.category)
        else:
            self.party = make_party_combo(db, self.cfg["kind"])
            self.party.currentIndexChanged.connect(self._party_changed)
            form.addRow(self.cfg["party_label"] + " *", self.party)
            self.info = QLabel()
            self.info.setObjectName("subtitle")
            form.addRow("", self.info)
        self.amount = QDoubleSpinBox()
        self.amount.setRange(0, 1e9)
        self.amount.setDecimals(2)
        self.amount.setGroupSeparatorShown(True)
        self.date = QDateEdit(QDate.currentDate())
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("dd-MM-yyyy")
        self.note = QLineEdit()
        form.addRow("Amount *", self.amount)
        form.addRow("Date", self.date)
        form.addRow("Note", self.note)
        lay.addLayout(form)
        self.error = QLabel("")
        self.error.setObjectName("error")
        self.error.setWordWrap(True)
        lay.addWidget(self.error)

        row = QHBoxLayout()
        row.addStretch()
        close = QPushButton("Close")
        close.setObjectName("secondary")
        close.clicked.connect(self.reject)
        save = QPushButton("Save")
        save.setDefault(True)
        save.clicked.connect(lambda: self._save(False))
        row.addWidget(close)
        row.addWidget(save)
        if mode != "expense":
            sp = QPushButton("Save && Print Voucher")
            sp.clicked.connect(lambda: self._save(True))
            row.addWidget(sp)
        lay.addLayout(row)

    def _party_changed(self, *_):
        pid = combo_party_id(self.party)
        if not pid:
            self.info.setText("")
            return
        fn = customer_balance if self.cfg["kind"] == "customer" else supplier_balance
        self.info.setText(f"{self.cfg['hint']} {money(fn(self.db.conn, pid))}")

    def _save(self, print_after):
        self.error.setText("")
        when = _stamp(self.date.date())
        try:
            if self.mode == "expense":
                payments.add_expense(self.db, self.category.currentText(), self.amount.value(),
                                     self.note.text(), when)
                voucher = None
            else:
                pid = combo_party_id(self.party)
                if not pid:
                    raise BusinessError(f"Please select a {self.cfg['party_label'].lower()}")
                voucher = self.cfg["action"](self.db, pid, self.amount.value(), self.note.text(), when)
        except BusinessError as exc:
            self.error.setText(str(exc))
            return
        if print_after and voucher:
            try:
                print_voucher(self.db, voucher)
            except Exception as exc:
                QMessageBox.warning(self, "Print", f"Saved ({voucher}), but printing failed:\n{exc}")
        else:
            QMessageBox.information(self, "Saved", "Saved." if not voucher else f"Saved. Voucher {voucher}.")
        # ready for the next entry
        self.amount.setValue(0)
        self.note.clear()
        if self.mode != "expense":
            self._party_changed()
