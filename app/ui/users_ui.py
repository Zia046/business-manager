"""Utilities > Staff Accounts (owner only): add staff, reset a password, disable / enable."""
from PySide6.QtWidgets import (QDialog, QFormLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QVBoxLayout)

from ..services import auth
from ..services.common import BusinessError
from .enter_safe import EnterSafeDialog
from .widgets import make_table, set_row


class AddStaffDialog(EnterSafeDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Add Staff Account")
        self.setMinimumWidth(420)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit()
        self.login_id = QLineEdit()
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        self.owner_pw = QLineEdit()
        self.owner_pw.setEchoMode(QLineEdit.Password)
        form.addRow("Staff name *", self.name)
        form.addRow("Login ID *", self.login_id)
        form.addRow("Staff password * (6+ letters)", self.password)
        form.addRow("Your (owner) password *", self.owner_pw)
        lay.addLayout(form)
        self.error = QLabel("")
        self.error.setObjectName("error")
        self.error.setWordWrap(True)
        lay.addWidget(self.error)
        save = QPushButton("Add")
        save.clicked.connect(self.save)
        lay.addWidget(save)

    def save(self):
        try:
            auth.add_staff(self.db, self.owner_pw.text(), self.name.text(), self.login_id.text(),
                           self.password.text())
        except BusinessError as exc:
            self.error.setText(str(exc))
            return
        self.accept()


class UsersDialog(QDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Staff Accounts")
        self.resize(640, 420)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Staff can sell and take recoveries, but cannot see purchase prices, profit, "
                             "accounts, backups or reset."))
        row = QHBoxLayout()
        for text, fn in (("Add Staff", self.add), ("Reset Password", self.reset), ("Disable / Enable", self.toggle)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch()
        lay.addLayout(row)
        self.table = make_table(["Login ID", "Name", "Role", "Status"], stretch_col=1)
        lay.addWidget(self.table)
        self.reload()

    def reload(self):
        rows = auth.list_users(self.db)
        self.table.setRowCount(len(rows))
        for i, u in enumerate(rows):
            set_row(self.table, i, [u["login_id"], u["name"] or "", u["role"].title(),
                                    "Active" if u["active"] else "Disabled"])

    def _selected(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "Select", "Select a staff account first.")
            return None
        return self.table.item(rows[0].row(), 0).text(), self.table.item(rows[0].row(), 2).text()

    def add(self):
        if AddStaffDialog(self.db, self).exec():
            self.reload()

    def _ask(self, label):
        text, ok = QInputDialog.getText(self, "Password", label, QLineEdit.Password)
        return text if ok else None

    def reset(self):
        sel = self._selected()
        if not sel:
            return
        if sel[1] != "Staff":
            QMessageBox.information(self, "Owner", "The owner changes his own password in "
                                    "Utilities > Change Password / Username.")
            return
        new = self._ask(f"New password for {sel[0]}:")
        owner = self._ask("Your (owner) password:") if new else None
        if not owner:
            return
        try:
            auth.reset_staff_password(self.db, owner, sel[0], new)
            QMessageBox.information(self, "Done", "Password changed.")
        except BusinessError as exc:
            QMessageBox.warning(self, "Cannot change", str(exc))

    def toggle(self):
        sel = self._selected()
        if not sel or sel[1] != "Staff":
            return
        active = self.table.item(self.table.currentRow(), 3).text() == "Active"
        owner = self._ask("Your (owner) password:")
        if not owner:
            return
        try:
            auth.set_staff_active(self.db, owner, sel[0], not active)
        except BusinessError as exc:
            QMessageBox.warning(self, "Cannot change", str(exc))
        self.reload()
