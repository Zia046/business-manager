"""Change Cash in Hand: owner only, and only after typing the owner's password."""
from PySide6.QtWidgets import QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout

from ..config import APP_NAME
from ..services import cash, reports as R
from ..services.common import BusinessError, is_owner
from .enter_safe import EnterSafeDialog


class CashAdjustDialog(EnterSafeDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Cash in Hand")
        self.setMinimumWidth(420)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        self.current = R.cash_in_hand(db)
        lay.addWidget(QLabel(f"Cash in Hand now: <b style='font-size:18px'>{self.current:,.2f}</b>"))
        note = QLabel("Count the cash in the drawer and type the real amount. The difference is written in the "
                      "Cash Book as 'Cash adjustment' (old entries are not changed).")
        note.setObjectName("subtitle")
        note.setWordWrap(True)
        lay.addWidget(note)
        form = QFormLayout()
        self.amount = QLineEdit(f"{self.current:.2f}")
        self.amount.selectAll()
        self.reason = QLineEdit(placeholderText="Reason (optional), e.g. opening cash / counted drawer")
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        self.password.setPlaceholderText("Admin password")
        form.addRow("New Cash in Hand *", self.amount)
        form.addRow("Reason", self.reason)
        form.addRow("Password *", self.password)
        lay.addLayout(form)
        self.error = QLabel("")
        self.error.setObjectName("error")
        self.error.setWordWrap(True)
        lay.addWidget(self.error)
        row = QHBoxLayout()
        save = QPushButton("Save")
        save.clicked.connect(self.save)
        close = QPushButton("Cancel")
        close.setObjectName("secondary")
        close.clicked.connect(self.reject)
        row.addWidget(save)
        row.addWidget(close)
        lay.addLayout(row)
        if not is_owner():                                   # staff never get here, but be safe
            save.setEnabled(False)
            self.error.setText("Only the owner can change Cash in Hand.")

    def save(self):
        try:
            diff = cash.set_cash_in_hand(self.db, self.amount.text().replace(",", ""), self.password.text(),
                                         self.reason.text())
        except BusinessError as e:
            self.error.setText(str(e))
            self.password.clear()
            return
        QMessageBox.information(self, APP_NAME, "Cash in Hand saved." if diff else "No change: same amount.")
        self.accept()
