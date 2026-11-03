"""Repair / service jobs screen."""
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout)

from ..services import reminders, repairs
from ..services.common import BusinessError
from .enter_safe import EnterSafeDialog
from .printing import print_repair_slip
from .whatsapp import send_whatsapp
from .widgets import make_table, money, selected_id, set_row


def _spin(value=0.0):
    s = QDoubleSpinBox()
    s.setRange(0, 1e9)
    s.setDecimals(2)
    s.setGroupSeparatorShown(True)
    s.setValue(value)
    return s


class NewJobDialog(EnterSafeDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.job_id = None
        self.setWindowTitle("New Repair Job")
        self.setMinimumWidth(480)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit()
        self.phone = QLineEdit()
        self.device = QLineEdit(placeholderText="e.g. Samsung A12")
        self.imei = QLineEdit(placeholderText="optional")
        self.problem = QPlainTextEdit()
        self.problem.setFixedHeight(70)
        self.estimate = _spin()
        self.advance = _spin()
        for label, w in (("Customer name *", self.name), ("Phone", self.phone), ("Device *", self.device),
                         ("IMEI", self.imei), ("Problem", self.problem), ("Estimate (Rs.)", self.estimate),
                         ("Advance taken (Rs.)", self.advance)):
            form.addRow(label, w)
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
        save = QPushButton("Save Job")
        save.clicked.connect(lambda: self._save(False))
        sp = QPushButton("Save && Print Slip")
        sp.clicked.connect(lambda: self._save(True))
        for b in (close, save, sp):
            row.addWidget(b)
        lay.addLayout(row)

    def _save(self, print_after):
        try:
            self.job_id = repairs.create_job(self.db, self.name.text(), self.phone.text(), self.device.text(),
                                             self.problem.toPlainText(), self.estimate.value(), self.advance.value(),
                                             self.imei.text())
        except BusinessError as exc:
            self.error.setText(str(exc))
            return
        if print_after:
            try:
                print_repair_slip(self.db, self.job_id)
            except Exception as exc:
                QMessageBox.warning(self, "Print", f"Job saved, but printing failed:\n{exc}")
        self.accept()


class UpdateDialog(EnterSafeDialog):
    """Change status (received / in repair / ready) and write the charges and parts cost."""
    def __init__(self, db, job, parent=None):
        super().__init__(parent)
        self.db, self.job = db, job
        self.setWindowTitle(f"Update {job['no']}")
        self.setMinimumWidth(420)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.status = QComboBox()
        for key in repairs.OPEN:
            self.status.addItem(repairs.STATUS_LABEL[key], key)
        self.status.setCurrentIndex(max(self.status.findData(job["status"]), 0))
        self.charges = _spin(job["charges"])
        self.parts = _spin(job["parts_cost"])
        form.addRow("Status", self.status)
        form.addRow("Final charges (Rs.)", self.charges)
        form.addRow("Parts cost (Rs.)", self.parts)
        lay.addLayout(form)
        self.error = QLabel("")
        self.error.setObjectName("error")
        lay.addWidget(self.error)
        ok = QPushButton("Save")
        ok.clicked.connect(self._save)
        lay.addWidget(ok)

    def _save(self):
        try:
            repairs.update_job(self.db, self.job["id"], status=self.status.currentData(),
                               charges=self.charges.value(), parts_cost=self.parts.value())
        except BusinessError as exc:
            self.error.setText(str(exc))
            return
        self.accept()


class DeliverDialog(EnterSafeDialog):
    def __init__(self, db, job, parent=None):
        super().__init__(parent)
        self.db, self.job = db, job
        self.setWindowTitle(f"Deliver {job['no']}")
        self.setMinimumWidth(420)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"{job['device']}  -  {job['customer_name']}\nAlready received: "
                             f"{money(job['received'])}"))
        form = QFormLayout()
        self.charges = _spin(job["charges"] or job["estimate"])
        self.parts = _spin(job["parts_cost"])
        self.payment = _spin(max((job["charges"] or job["estimate"]) - job["received"], 0))
        self.charges.valueChanged.connect(lambda v: self.payment.setValue(max(v - job["received"], 0)))
        form.addRow("Final charges (Rs.)", self.charges)
        form.addRow("Parts cost (Rs.)", self.parts)
        form.addRow("Payment received now (Rs.)", self.payment)
        lay.addLayout(form)
        self.error = QLabel("")
        self.error.setObjectName("error")
        self.error.setWordWrap(True)
        lay.addWidget(self.error)
        ok = QPushButton("Deliver Phone")
        ok.clicked.connect(self._save)
        lay.addWidget(ok)

    def _save(self):
        try:
            repairs.deliver(self.db, self.job["id"], self.charges.value(), self.parts.value(), self.payment.value())
        except BusinessError as exc:
            self.error.setText(str(exc))
            return
        self.accept()


class RepairsWindow(EnterSafeDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.jobs = []
        self.setWindowTitle("Repair Jobs")
        self.resize(1100, 600)
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.filter = QComboBox()
        self.filter.addItem("Open jobs", "open")
        for key in ("received", "in_progress", "ready", "delivered", "cancelled"):
            self.filter.addItem(repairs.STATUS_LABEL[key], key)
        self.filter.addItem("All jobs", None)
        self.filter.currentIndexChanged.connect(self.reload)
        self.search = QLineEdit(placeholderText="Search job no, customer, phone, device, IMEI...")
        self.search.textChanged.connect(self.reload)
        top.addWidget(self.filter)
        top.addWidget(self.search, 1)
        lay.addLayout(top)
        row = QHBoxLayout()
        for text, fn, name in (("New Job", self.new_job, None), ("Update / Status", self.update, "secondary"),
                               ("Deliver", self.deliver, None), ("Take Due Payment", self.pay, "secondary"),
                               ("Print Slip", self.slip, "secondary"), ("WhatsApp: Phone Ready", self.whatsapp,
                                                                          "secondary"),
                               ("Cancel Job", self.cancel, "secondary")):
            b = QPushButton(text)
            if name:
                b.setObjectName(name)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch()
        lay.addLayout(row)
        self.table = make_table(["ID", "Job No", "Date", "Customer", "Phone", "Device", "Problem", "Estimate",
                                 "Charges", "Received", "Due", "Status"], stretch_col=6)
        lay.addWidget(self.table)
        self.info = QLabel()
        lay.addWidget(self.info)
        self.reload()

    def reload(self, *_):
        self.jobs = repairs.list_jobs(self.db, self.filter.currentData(), self.search.text())
        self.table.setRowCount(len(self.jobs))
        for i, j in enumerate(self.jobs):
            ready = j["status"] == "ready"
            set_row(self.table, i, [j["id"], j["no"], j["date"][:10], j["customer_name"], j["phone"] or "",
                                    j["device"], j["problem"] or "", money(j["estimate"]), money(j["charges"]),
                                    money(j["received"]), money(j["due"]) if j["due"] else "",
                                    repairs.STATUS_LABEL[j["status"]]],
                    (7, 8, 9, 10), QColor("#e6f6e6") if ready else (QColor("#fdecea") if j["due"] else None))
        open_n = sum(1 for j in self.jobs if j["status"] in repairs.OPEN)
        self.info.setText(f"{len(self.jobs)} jobs shown   |   open: {open_n}   |   "
                          f"money still to receive: {money(sum(j['due'] for j in self.jobs))}")

    def _job(self):
        jid = selected_id(self.table)
        if jid is None:
            QMessageBox.information(self, "Select", "Select a job first.")
            return None
        return next(j for j in self.jobs if j["id"] == jid)

    def new_job(self):
        if NewJobDialog(self.db, self).exec():
            self.reload()

    def update(self):
        j = self._job()
        if j and j["status"] not in repairs.OPEN:
            QMessageBox.information(self, "Job", "A delivered or cancelled job cannot be changed.")
        elif j and UpdateDialog(self.db, j, self).exec():
            self.reload()

    def deliver(self):
        j = self._job()
        if j and j["status"] not in repairs.OPEN:
            QMessageBox.information(self, "Job", "This job is already delivered or cancelled.")
        elif j and DeliverDialog(self.db, j, self).exec():
            self.reload()

    def pay(self):
        j = self._job()
        if not j:
            return
        from PySide6.QtWidgets import QInputDialog
        amount, ok = QInputDialog.getDouble(self, "Take payment", f"Amount due: {money(j['due'])}\nReceived now:",
                                            j["due"], 0, 1e9, 2)
        if ok and amount > 0:
            try:
                repairs.receive_payment(self.db, j["id"], amount)
            except BusinessError as exc:
                QMessageBox.warning(self, "Payment", str(exc))
            self.reload()

    def slip(self):
        j = self._job()
        if j:
            try:
                print_repair_slip(self.db, j["id"])
            except Exception as exc:
                QMessageBox.warning(self, "Print", f"Could not print:\n{exc}")

    def whatsapp(self):
        j = self._job()
        if j:
            from .whatsapp import send_whatsapp as send
            phone, text = reminders.repair_ready_message(self.db, j["id"])
            send(self, phone, text)

    def cancel(self):
        j = self._job()
        if not j:
            return
        if QMessageBox.question(self, "Cancel job", f"Cancel {j['no']}? Any advance ({money(j['received'])}) is "
                                "returned to the customer.") != QMessageBox.Yes:
            return
        try:
            repairs.cancel_job(self.db, j["id"])
        except BusinessError as exc:
            QMessageBox.warning(self, "Cancel", str(exc))
        self.reload()
