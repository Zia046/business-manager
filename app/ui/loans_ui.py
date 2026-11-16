"""Cash Loan: money lent to a person, what he has brought back and what is still outstanding."""
from PySide6.QtCore import QDate
from PySide6.QtWidgets import (QCheckBox, QDateEdit, QDialog, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QPushButton, QVBoxLayout)

from ..config import APP_NAME
from ..services import loans
from ..services.common import BusinessError
from .enter_safe import EnterSafeDialog
from .payments_ui import _stamp
from .theme import C_RED
from .widgets import make_table, money, set_row


def _amount_box():
    box = QDoubleSpinBox()
    box.setRange(0, 1e9)
    box.setDecimals(2)
    box.setGroupSeparatorShown(True)
    return box


def _date_box():
    d = QDateEdit(QDate.currentDate())
    d.setCalendarPopup(True)
    d.setDisplayFormat("dd-MM-yyyy")
    return d


def _buttons(lay, dialog, save_text, on_save):
    row = QHBoxLayout()
    row.addStretch()
    close = QPushButton("Cancel")
    close.setObjectName("secondary")
    close.clicked.connect(dialog.reject)
    save = QPushButton(save_text)
    save.clicked.connect(on_save)
    row.addWidget(close)
    row.addWidget(save)
    lay.addLayout(row)


class LoanDialog(EnterSafeDialog):
    """Give a cash loan. `person` (a row of loans.people) fills the form for another loan to the same person."""

    def __init__(self, db, person=None, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Cash Loan - Give Loan")
        self.setMinimumWidth(480)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(26, 20, 26, 20)
        person = person or {}
        form = QFormLayout()
        self.name = QLineEdit(person.get("name") or "")
        self.cnic = QLineEdit(person.get("cnic") or "")
        self.cnic.setPlaceholderText("13 digits, e.g. 15101-1234567-1")
        self.phone = QLineEdit(person.get("phone") or "")
        self.address = QLineEdit(person.get("address") or "")
        self.amount = _amount_box()
        self.date = _date_box()
        self.note = QLineEdit(placeholderText="Optional")
        form.addRow("Person Name *", self.name)
        form.addRow("CNIC Number", self.cnic)
        form.addRow("Mobile Number", self.phone)
        form.addRow("Address", self.address)
        form.addRow("Loan Amount *", self.amount)
        form.addRow("Loan Date", self.date)
        form.addRow("Remarks", self.note)
        lay.addLayout(form)
        hint = QLabel("The amount goes out of Cash in Hand and is added to Outstanding (Cash Loan).")
        hint.setObjectName("subtitle")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        self.error = QLabel("")
        self.error.setObjectName("error")
        self.error.setWordWrap(True)
        lay.addWidget(self.error)
        _buttons(lay, self, "Save Loan", self.save)
        if person:
            self.amount.setFocus()

    def save(self):
        try:
            loans.give_loan(self.db, self.name.text(), self.amount.value(), cnic=self.cnic.text(),
                            phone=self.phone.text(), address=self.address.text(), note=self.note.text(),
                            date=_stamp(self.date.date()))
        except BusinessError as exc:
            self.error.setText(str(exc))
            return
        self.accept()


class RepaymentDialog(EnterSafeDialog):
    def __init__(self, db, person, parent=None):
        super().__init__(parent)
        self.db, self.person = db, person
        self.setWindowTitle("Cash Loan - Receive Repayment")
        self.setMinimumWidth(440)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(26, 20, 26, 20)
        lay.addWidget(QLabel(f"<b style='font-size:16px'>{person['name']}</b>"))
        due = QLabel(f"Outstanding loan: <b style='font-size:18px; color:{C_RED}'>{money(person['balance'])}</b>")
        lay.addWidget(due)
        form = QFormLayout()
        self.amount = _amount_box()
        self.amount.setMaximum(person["balance"])           # can never be more than what is still owed
        self.date = _date_box()
        self.note = QLineEdit(placeholderText="Optional")
        self.left = QLabel("")
        self.left.setObjectName("subtitle")
        form.addRow("Amount Received *", self.amount)
        form.addRow("", self.left)
        form.addRow("Date", self.date)
        form.addRow("Remarks", self.note)
        lay.addLayout(form)
        self.amount.valueChanged.connect(
            lambda v: self.left.setText(f"Remaining after this: {money(max(person['balance'] - v, 0))}"))
        self.error = QLabel("")
        self.error.setObjectName("error")
        self.error.setWordWrap(True)
        lay.addWidget(self.error)
        full = QPushButton("Full Amount")
        full.setObjectName("secondary")
        full.clicked.connect(lambda: self.amount.setValue(person["balance"]))
        lay.addWidget(full)
        _buttons(lay, self, "Save Repayment", self.save)

    def save(self):
        try:
            left = loans.receive_repayment(self.db, self.person["id"], self.amount.value(), self.note.text(),
                                           _stamp(self.date.date()))
        except BusinessError as exc:
            self.error.setText(str(exc))
            return
        QMessageBox.information(self, APP_NAME, f"Saved. Remaining outstanding: {money(left)}")
        self.accept()


class LoanHistoryDialog(QDialog):
    def __init__(self, db, person, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Cash Loan History - {person['name']}")
        self.resize(720, 480)
        lay = QVBoxLayout(self)
        info = " | ".join(x for x in (person["name"], f"CNIC {person['cnic']}" if person["cnic"] else "",
                                      person["phone"] or "", person["address"] or "") if x)
        lay.addWidget(QLabel(f"<b>{info}</b>"))
        table = make_table(["Date", "Type", "Loan Given", "Received Back", "Balance", "Remarks"], stretch_col=5)
        rows = loans.history(db, person["id"])
        names = {"loan": "Loan given", "repayment": "Repayment", "adjustment": "Adjustment"}
        table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            set_row(table, i, [r["date"][:16], names[r["kind"]], money(r["amount"]) if r["kind"] == "loan" else "",
                               money(r["amount"]) if r["kind"] != "loan" else "", money(r["balance"]),
                               r["note"] or ""], (2, 3, 4))
        lay.addWidget(table, 1)
        bottom = QHBoxLayout()
        bottom.addWidget(QLabel(f"Total given: <b>{money(person['given'])}</b> &nbsp;&nbsp; Received back: "
                                f"<b>{money(person['returned'])}</b> &nbsp;&nbsp; Outstanding: "
                                f"<b style='color:{C_RED}'>{money(person['balance'])}</b>"), 1)
        close = QPushButton("Close")
        close.setObjectName("secondary")
        close.clicked.connect(self.reject)
        bottom.addWidget(close)
        lay.addLayout(bottom)


class CashLoanWindow(QDialog):
    HEADERS = ["ID", "Person Name", "CNIC", "Mobile", "Total Loan", "Received Back", "Outstanding"]

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db, self.rows = db, []
        self.setWindowTitle("Cash Loan")
        self.resize(980, 600)
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.search = QLineEdit(placeholderText="Search name, CNIC or mobile...")
        self.search.textChanged.connect(self.reload)
        self.only_open = QCheckBox("Only outstanding")
        self.only_open.toggled.connect(self.reload)
        top.addWidget(self.search, 1)
        top.addWidget(self.only_open)
        lay.addLayout(top)
        self.table = make_table(self.HEADERS, stretch_col=1)
        self.table.doubleClicked.connect(self._history)
        lay.addWidget(self.table, 1)
        self.total = QLabel("")
        self.total.setStyleSheet("font-size: 15px; font-weight: 700;")
        lay.addWidget(self.total)
        row = QHBoxLayout()
        for text, fn, secondary in (("New Cash Loan", self._new, False), ("Receive Repayment", self._repay, False),
                                    ("History", self._history, True)):
            b = QPushButton(text)
            if secondary:
                b.setObjectName("secondary")
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch()
        close = QPushButton("Close")
        close.setObjectName("secondary")
        close.clicked.connect(self.reject)
        row.addWidget(close)
        lay.addLayout(row)
        self.reload()

    def reload(self, *_):
        self.rows = loans.people(self.db, self.only_open.isChecked(), self.search.text())
        self.table.setRowCount(len(self.rows))
        for i, r in enumerate(self.rows):
            set_row(self.table, i, [r["id"], r["name"], r["cnic"] or "", r["phone"] or "", money(r["given"]),
                                    money(r["returned"]), money(r["balance"])], (4, 5, 6))
        self.total.setText(f"Total Cash Loan Outstanding: {money(loans.total_outstanding(self.db))}")

    def _selected(self):
        sel = self.table.selectionModel().selectedRows()
        return self.rows[sel[0].row()] if sel else None

    def _new(self):
        if LoanDialog(self.db, self._selected(), self).exec():
            self.reload()

    def _repay(self):
        person = self._selected()
        if not person:
            QMessageBox.information(self, APP_NAME, "Select the person first.")
            return
        if person["balance"] <= 0:
            QMessageBox.information(self, APP_NAME, f"{person['name']} has no outstanding loan.")
            return
        if RepaymentDialog(self.db, person, self).exec():
            self.reload()

    def _history(self, *_):
        person = self._selected()
        if not person:
            QMessageBox.information(self, APP_NAME, "Select the person first.")
            return
        LoanHistoryDialog(self.db, person, self).exec()
