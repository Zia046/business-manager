"""Cash Recovery: pick a customer, see the last month of the khata and the balance, enter the recovery."""
from datetime import datetime, timedelta

from PySide6.QtCore import QDate, QDateTime
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QDateEdit, QDoubleSpinBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QVBoxLayout)

from ..services import payments, reminders, reports
from ..services.common import BusinessError
from .enter_safe import EnterSafeDialog
from .party_picker import combo_party_id, make_party_combo
from .printing import print_voucher
from .whatsapp import send_whatsapp
from .widgets import make_table, money, set_row

_LABELS = {"invoice": "Sale", "receipt": "Cash received", "customer_payment": "Paid to customer",
           "sale_return": "Sale return", "adjustment": "Balance cleared"}


def _stamp(qdate: QDate) -> str:
    return f"{qdate.toString('yyyy-MM-dd')} {QDateTime.currentDateTime().toString('HH:mm:ss')}"


class CashRecoveryDialog(EnterSafeDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self._current = 0.0
        self.setWindowTitle("Cash Recovery")
        self.resize(860, 640)
        root = QVBoxLayout(self)

        row = QHBoxLayout()
        row.addWidget(QLabel("Customer:"))
        self.party = make_party_combo(db, "customer")
        self.party.currentIndexChanged.connect(self._party_changed)
        row.addWidget(self.party, 1)
        root.addLayout(row)

        self.period = QLabel("Select a customer: the khata of the last 1 month opens here.")
        self.period.setObjectName("subtitle")
        root.addWidget(self.period)
        self.table = make_table(["Date", "Description", "Debit (sale)", "Credit (received)", "Balance"])
        root.addWidget(self.table, 1)

        self.balance = QLabel("Current balance: -")
        self.balance.setStyleSheet("font-size: 20px; font-weight: 800; color: #2563EB;")
        root.addWidget(self.balance)

        grid = QGridLayout()
        self.amount = QDoubleSpinBox()
        self.amount.setRange(0, 1e9)
        self.amount.setDecimals(2)
        self.amount.setGroupSeparatorShown(True)
        self.amount.valueChanged.connect(self._after_amount)
        self.date = QDateEdit(QDate.currentDate())
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("dd-MM-yyyy")
        self.note = QLineEdit()
        self.after = QLabel("")
        self.after.setStyleSheet("font-weight: 700;")
        grid.addWidget(QLabel("New recovery amount *"), 0, 0)
        grid.addWidget(self.amount, 0, 1)
        grid.addWidget(QLabel("Balance after this recovery"), 0, 2)
        grid.addWidget(self.after, 0, 3)
        grid.addWidget(QLabel("Date"), 1, 0)
        grid.addWidget(self.date, 1, 1)
        grid.addWidget(QLabel("Note"), 1, 2)
        grid.addWidget(self.note, 1, 3)
        root.addLayout(grid)

        self.error = QLabel("")
        self.error.setObjectName("error")
        self.error.setWordWrap(True)
        root.addWidget(self.error)
        btns = QHBoxLayout()
        btns.addStretch()
        close = QPushButton("Close")
        close.setObjectName("secondary")
        close.clicked.connect(self.reject)
        save = QPushButton("Save")
        save.clicked.connect(lambda: self._save(False))
        sp = QPushButton("Save && Print Voucher")
        sp.clicked.connect(lambda: self._save(True))
        wa = QPushButton("WhatsApp Reminder")
        wa.setObjectName("secondary")
        wa.clicked.connect(self._whatsapp)
        btns.insertWidget(0, wa)
        for b in (close, save, sp):
            btns.addWidget(b)
        root.addLayout(btns)
        self.party.setFocus()

    # ---- khata ----
    def _party_changed(self, *_):
        pid = combo_party_id(self.party)
        self.table.setRowCount(0)
        self.error.setText("")
        if not pid:
            self.balance.setText("Current balance: -")
            self.after.setText("")
            return
        since = datetime.now() - timedelta(days=30)
        led = reports.customer_ledger(self.db, pid, since.strftime("%Y-%m-%d"), None)
        rows = led["rows"]
        self.table.setRowCount(len(rows) + 1)
        set_row(self.table, 0, [since.strftime("%Y-%m-%d"), "Balance before this period", "", "",
                                money(led["period_opening"])], (2, 3, 4), QColor("#F3F5F9"))
        for i, r in enumerate(rows, start=1):
            base = _LABELS.get(r["ref_type"], r["ref_type"])
            desc = f"{base}: {r['note']}" if r.get("note") else base
            set_row(self.table, i, [r["date"][:16], desc, money(r["debit"]) if r["debit"] else "",
                                    money(r["credit"]) if r["credit"] else "", money(r["balance"])], (2, 3, 4))
        self.table.scrollToBottom()
        self._current = led["closing"]
        self.period.setText(f"{led['party']['name']}  -  transactions of the last 1 month "
                            f"({len(rows)} entries)")
        self.balance.setText(f"Current balance (to receive): {money(self._current)}")
        self._after_amount()

    def _after_amount(self, *_):
        if combo_party_id(self.party):
            self.after.setText(money(round(self._current - self.amount.value(), 2)))

    def _whatsapp(self):
        pid = combo_party_id(self.party)
        if not pid:
            self.error.setText("Please select a customer")
            return
        phone, text = reminders.balance_message(self.db, pid)
        send_whatsapp(self, phone, text)

    def _save(self, print_after):
        self.error.setText("")
        pid = combo_party_id(self.party)
        if not pid:
            self.error.setText("Please select a customer")
            return
        try:
            voucher = payments.receive_from_customer(self.db, pid, self.amount.value(), self.note.text(),
                                                     _stamp(self.date.date()))
        except BusinessError as exc:
            self.error.setText(str(exc))
            return
        if print_after:
            try:
                print_voucher(self.db, voucher)
            except Exception as exc:
                QMessageBox.warning(self, "Print", f"Saved ({voucher}), but printing failed:\n{exc}")
        else:
            QMessageBox.information(self, "Saved", f"Recovery saved. Voucher {voucher}.")
        self.amount.setValue(0)
        self.note.clear()
        self._party_changed()           # khata shows the new entry and the reduced balance
