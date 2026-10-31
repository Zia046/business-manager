"""Customers and Suppliers screen (same layout, different `kind`)."""
from PySide6.QtWidgets import (QDialog, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPushButton, QVBoxLayout)

from ..services import masters
from ..services.common import BusinessError, customer_balance, supplier_balance
from .widgets import make_table, money, selected_id, set_row


class PartyForm(QDialog):
    def __init__(self, db, kind, party=None, parent=None):
        super().__init__(parent)
        self.db, self.kind, self.party = db, kind, party
        self.saved_id = None
        self.setWindowTitle(("Edit " if party else "New ") + kind.title())
        self.setMinimumWidth(420)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(26, 22, 26, 22)
        form = QFormLayout()
        form.addRow("ID", QLabel(str(party["id"]) if party else "Auto (system generated)"))
        self.name = QLineEdit(party["name"] if party else "")
        self.phone = QLineEdit((party["phone"] or "") if party else "")
        self.address = QLineEdit((party["address"] or "") if party else "")
        self.opening = QDoubleSpinBox()
        self.opening.setRange(-1e9, 1e9)
        self.opening.setDecimals(2)
        self.opening.setValue(party["opening_balance"] if party else 0)
        form.addRow("Name *", self.name)
        form.addRow("Phone", self.phone)
        form.addRow("Address", self.address)
        form.addRow("Opening Balance", self.opening)
        lay.addLayout(form)
        hint = "Positive = customer owes you." if kind == "customer" else "Positive = you owe the supplier."
        h = QLabel(hint)
        h.setObjectName("subtitle")
        lay.addWidget(h)
        self.error = QLabel("")
        self.error.setObjectName("error")
        lay.addWidget(self.error)
        save = QPushButton("Save")
        save.setDefault(True)
        save.clicked.connect(self.save)
        lay.addWidget(save)

    def save(self):
        try:
            if self.party:
                masters.update_party(self.db, self.party["id"], self.name.text(), self.phone.text(),
                                     self.address.text(), self.opening.value())
                self.saved_id = self.party["id"]
            else:
                self.saved_id = masters.add_party(self.db, self.kind, self.name.text(), self.phone.text(),
                                                  self.address.text(), self.opening.value())
        except BusinessError as exc:
            self.error.setText(str(exc))
            return
        self.accept()


class PartiesWindow(QDialog):
    def __init__(self, db, kind, parent=None):
        super().__init__(parent)
        self.db, self.kind = db, kind
        plural = "Customers" if kind == "customer" else "Suppliers"
        self.setWindowTitle(plural)
        self.resize(860, 560)
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.search = QLineEdit(placeholderText="Search by name, phone or ID...")
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
        self.table = make_table(["ID", "Name", "Phone", "Address", "Balance"])
        self.table.doubleClicked.connect(self.edit)
        lay.addWidget(self.table)
        self.total = QLabel()
        self.total.setStyleSheet("font-weight: 700; font-size: 15px;")
        lay.addWidget(self.total)
        self.reload()

    def reload(self):
        rows = [r for r in masters.search_parties(self.db, self.kind, self.search.text())
                if not r["is_walkin"]]
        fn = customer_balance if self.kind == "customer" else supplier_balance
        self.table.setRowCount(len(rows))
        total = 0.0
        for i, r in enumerate(rows):
            bal = fn(self.db.conn, r["id"])
            total += bal
            set_row(self.table, i, [r["id"], r["name"], r["phone"], r["address"], money(bal)], (4,))
        label = "Total receivable" if self.kind == "customer" else "Total payable"
        self.total.setText(f"{len(rows)} records     {label}: {money(total)}")

    def add(self):
        if PartyForm(self.db, self.kind, parent=self).exec():
            self.reload()

    def _selected_party(self):
        pid = selected_id(self.table)
        if pid is None:
            QMessageBox.information(self, "Select", "Please select a row first.")
            return None
        return self.db.one("SELECT * FROM parties WHERE id=?", (pid,))

    def edit(self, *_):
        p = self._selected_party()
        if p and PartyForm(self.db, self.kind, p, self).exec():
            self.reload()

    def delete(self):
        p = self._selected_party()
        if not p:
            return
        if QMessageBox.question(self, "Delete", f"Delete '{p['name']}'?\n"
                                "(If it has transactions it will only be hidden, history is kept.)"
                                ) != QMessageBox.Yes:
            return
        try:
            result = masters.delete_party(self.db, p["id"])
        except BusinessError as exc:
            QMessageBox.warning(self, "Cannot delete", str(exc))
            return
        if result == "deactivated":
            QMessageBox.information(self, "Done", "Account has transactions, so it was hidden "
                                    "instead of deleted. History is kept.")
        self.reload()
