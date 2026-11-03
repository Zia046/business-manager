"""Installments (qist): list of plans, new plan, schedule, receive qist, WhatsApp reminder."""
from datetime import date

from PySide6.QtCore import QDate
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QComboBox, QDateEdit, QDialog, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel,
                               QMessageBox, QPushButton, QSpinBox, QVBoxLayout)

from ..services import installments, reminders
from ..services.common import BusinessError, add_months, customer_balance
from .cash_recovery import CashRecoveryDialog
from .enter_safe import EnterSafeDialog
from .party_picker import combo_party_id, make_party_combo
from .whatsapp import send_whatsapp
from .widgets import make_table, money, selected_id, set_row

STATUS = {"active": "Running", "closed": "Completed", "cancelled": "Cancelled"}


class NewPlanDialog(EnterSafeDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("New Installment Plan")
        self.resize(560, 560)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.party = make_party_combo(db, "customer")
        self.party.currentIndexChanged.connect(self._party_changed)
        self.owes = QLabel("")
        self.invoice = QComboBox()
        self.invoice.currentIndexChanged.connect(self._invoice_changed)
        self.principal = QDoubleSpinBox()
        self.principal.setRange(0, 1e9)
        self.principal.setDecimals(2)
        self.principal.setGroupSeparatorShown(True)
        self.principal.valueChanged.connect(self._preview)
        self.count = QSpinBox()
        self.count.setRange(1, 60)
        self.count.setValue(6)
        self.count.setSuffix(" installments")
        self.count.valueChanged.connect(self._preview)
        self.first = QDateEdit(QDate.currentDate().addMonths(1))
        self.first.setCalendarPopup(True)
        self.first.setDisplayFormat("dd-MM-yyyy")
        self.first.dateChanged.connect(self._preview)
        form.addRow("Customer *", self.party)
        form.addRow("Customer owes", self.owes)
        form.addRow("For invoice (optional)", self.invoice)
        form.addRow("Amount to divide *", self.principal)
        form.addRow("Number of installments", self.count)
        form.addRow("First due date", self.first)
        lay.addLayout(form)
        self.table = make_table(["#", "Due date", "Amount"], stretch_col=1)
        lay.addWidget(self.table, 1)
        self.error = QLabel("")
        self.error.setObjectName("error")
        self.error.setWordWrap(True)
        lay.addWidget(self.error)
        row = QHBoxLayout()
        row.addStretch()
        close = QPushButton("Close")
        close.setObjectName("secondary")
        close.clicked.connect(self.reject)
        ok = QPushButton("Create Plan")
        ok.clicked.connect(self._create)
        row.addWidget(close)
        row.addWidget(ok)
        lay.addLayout(row)

    def _party_changed(self, *_):
        pid = combo_party_id(self.party)
        self.invoice.blockSignals(True)
        self.invoice.clear()
        self.invoice.addItem("-- whole balance / no invoice --", None)
        if pid:
            bal = customer_balance(self.db.conn, pid)
            self.owes.setText(money(bal))
            self.principal.setValue(max(bal, 0))
            for r in self.db.query("SELECT id, no, date, total, paid FROM invoices WHERE party_id=? "
                                   "AND status='active' AND total-paid>0.004 ORDER BY id DESC LIMIT 100", (pid,)):
                self.invoice.addItem(f"{r['no']}  {r['date'][:10]}  credit {money(r['total'] - r['paid'])}",
                                     (r["id"], r["total"] - r["paid"]))
        self.invoice.blockSignals(False)
        self._preview()

    def _invoice_changed(self, *_):
        data = self.invoice.currentData()
        if data:
            self.principal.setValue(data[1])
        self._preview()

    def _first(self) -> str:
        return self.first.date().toString("yyyy-MM-dd")

    def _preview(self, *_):
        self.error.setText("")
        try:
            rows = installments.preview(self.principal.value(), self.count.value(), self._first())
        except BusinessError:
            self.table.setRowCount(0)
            return
        self.table.setRowCount(len(rows))
        for i, (seq, due, amount) in enumerate(rows):
            set_row(self.table, i, [seq, due, money(amount)], (2,))

    def _create(self):
        pid = combo_party_id(self.party)
        if not pid:
            self.error.setText("Select a customer.")
            return
        data = self.invoice.currentData()
        try:
            installments.create_plan(self.db, pid, self.principal.value(), self.count.value(), self._first(),
                                     invoice_id=data[0] if data else None)
        except BusinessError as exc:
            self.error.setText(str(exc))
            return
        self.accept()


class ScheduleDialog(EnterSafeDialog):
    def __init__(self, db, plan_id, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Installment Schedule")
        self.resize(620, 420)
        lay = QVBoxLayout(self)
        table = make_table(["#", "Due date", "Amount", "Paid", "Remaining", "Status"], stretch_col=1)
        lay.addWidget(table)
        rows = installments.schedule(db, plan_id)
        today = date.today().isoformat()
        table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            left = round(r["amount"] - r["paid"], 2)
            status = "Paid" if left <= 0.004 else ("LATE" if r["due_date"] < today else
                                                    ("Part paid" if r["paid"] else "Pending"))
            set_row(table, i, [r["seq"], r["due_date"], money(r["amount"]), money(r["paid"]), money(left), status],
                    (2, 3, 4), QColor("#fdecea") if status == "LATE" else None)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        lay.addWidget(close)


class QistWindow(EnterSafeDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Installments (Qist)")
        self.resize(1000, 580)
        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        for text, fn, name in (("New Plan", self.new_plan, None), ("View Schedule", self.view, "secondary"),
                               ("Receive Qist", self.receive, None),
                               ("WhatsApp Reminder", self.whatsapp, "secondary"),
                               ("Cancel Plan", self.cancel, "secondary")):
            b = QPushButton(text)
            if name:
                b.setObjectName(name)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch()
        lay.addLayout(row)
        self.table = make_table(["ID", "Plan", "Customer", "Invoice", "Total", "Paid", "Remaining", "Next due",
                                 "Status"], stretch_col=2)
        self.table.doubleClicked.connect(self.view)
        lay.addWidget(self.table)
        self.msg = QLabel("Cash received from a customer (Cash Recovery) is counted automatically towards "
                          "his oldest unpaid installment.")
        self.msg.setObjectName("subtitle")
        self.msg.setWordWrap(True)
        lay.addWidget(self.msg)
        self.reload()

    def reload(self):
        self.plans = installments.list_plans(self.db)
        self.table.setRowCount(len(self.plans))
        today = date.today().isoformat()
        for i, p in enumerate(self.plans):
            left = round(p["principal"] - p["paid"], 2) if p["status"] == "active" else 0
            late = p["status"] == "active" and p["next_due"] and p["next_due"] < today
            set_row(self.table, i, [p["id"], p["no"], p["customer"], p["invoice_no"] or "", money(p["principal"]),
                                    money(p["paid"]), money(left), p["next_due"] or "", STATUS[p["status"]]],
                    (4, 5, 6), QColor("#fdecea") if late else None)

    def _plan(self):
        pid = selected_id(self.table)
        if pid is None:
            QMessageBox.information(self, "Select", "Select a plan first.")
            return None
        return next(p for p in self.plans if p["id"] == pid)

    def new_plan(self):
        if NewPlanDialog(self.db, self).exec():
            self.reload()

    def view(self, *_):
        p = self._plan()
        if p:
            ScheduleDialog(self.db, p["id"], self).exec()

    def receive(self):
        CashRecoveryDialog(self.db, self).exec()
        self.reload()

    def whatsapp(self):
        p = self._plan()
        if p:
            phone, text = reminders.qist_message(self.db, p["party_id"])
            send_whatsapp(self, phone, text)

    def cancel(self):
        p = self._plan()
        if not p:
            return
        if QMessageBox.question(self, "Cancel plan", f"Cancel plan {p['no']}?\n(Only possible if nothing is "
                                "paid yet. The customer's balance is not changed.)") != QMessageBox.Yes:
            return
        try:
            installments.cancel_plan(self.db, p["id"])
        except BusinessError as exc:
            QMessageBox.warning(self, "Cancel plan", str(exc))
        self.reload()
