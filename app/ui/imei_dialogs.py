"""IMEI entry windows. IMEI rules live in services/imei.py (digits only, 10-100 digits, single/double)."""
from PySide6.QtCore import QRegularExpression, Qt
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QPlainTextEdit,
                               QVBoxLayout)

from ..services import imei
from ..services.common import BusinessError


class SaleImeiDialog(QDialog):
    """IMEI of ONE phone (sale, or a returned phone). Single phone: one box. Double: two boxes."""

    def __init__(self, parent, product_name, mode, checker=None, title="Enter IMEI"):
        super().__init__(parent)
        self.mode, self.checker, self.value = mode, checker, None
        self.setWindowTitle(title)
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        head = QLabel(f"<b>{product_name}</b><br>"
                      + ("This phone has <b>two</b> IMEI numbers - type both." if mode == "double"
                         else "Type the IMEI number of this phone."))
        head.setWordWrap(True)
        lay.addWidget(head)
        form = QFormLayout()
        digits = QRegularExpressionValidator(QRegularExpression("[0-9]*"))
        self.i1 = QLineEdit(placeholderText="10 to 100 digits")
        self.i1.setValidator(digits)
        form.addRow("IMEI 1" if mode == "double" else "IMEI", self.i1)
        self.i2 = None
        if mode == "double":
            self.i2 = QLineEdit(placeholderText="10 to 100 digits (different from IMEI 1)")
            self.i2.setValidator(digits)
            form.addRow("IMEI 2", self.i2)
        lay.addLayout(form)
        self.error = QLabel("")
        self.error.setObjectName("error")
        self.error.setWordWrap(True)
        lay.addWidget(self.error)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.accepted.connect(self._accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)
        self.i1.setFocus()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            w = self.focusWidget()
            if w is self.i1 and self.i2 is not None:
                self.i2.setFocus()          # Enter in IMEI 1 -> IMEI 2
            else:
                self._accept()              # Enter in the last box -> OK
            event.accept()
            return
        super().keyPressEvent(event)

    def _accept(self):
        try:
            i1, i2 = imei.unit(self.i1.text(), self.i2.text() if self.i2 else None, self.mode)
            if self.checker:
                self.checker(i1, i2)
        except BusinessError as exc:
            self.error.setText(str(exc))
            return
        self.value = (i1, i2)
        self.accept()


class PurchaseImeiDialog(QDialog):
    """IMEI numbers of many phones at once: one phone per line (double phones: two numbers per line)."""

    def __init__(self, parent, product_name, mode, checker=None):
        super().__init__(parent)
        self.mode, self.checker, self.value = mode, checker, None
        self.setWindowTitle("IMEI numbers")
        self.resize(520, 420)
        lay = QVBoxLayout(self)
        how = ("Type <b>two</b> IMEI numbers on each line (IMEI 1, then IMEI 2, separated by a space or comma)."
               if mode == "double" else "Type <b>one</b> IMEI number on each line.")
        head = QLabel(f"<b>{product_name}</b><br>{how}<br>Each number must be 10 to 100 digits. "
                      "One line = one phone.")
        head.setWordWrap(True)
        lay.addWidget(head)
        self.text = QPlainTextEdit()
        self.text.textChanged.connect(self._live)
        lay.addWidget(self.text, 1)
        self.status = QLabel("0 phones")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.accepted.connect(self._accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)
        self.text.setFocus()

    def _live(self):
        try:
            n = len(imei.parse_lines(self.text.toPlainText(), self.mode))
            self.status.setStyleSheet("")
            self.status.setText(f"{n} phone(s) - quantity will be {n}")
        except BusinessError as exc:
            self.status.setStyleSheet("color: #DC2626; font-weight: 600;")
            self.status.setText(str(exc))

    def _accept(self):
        try:
            units = imei.parse_lines(self.text.toPlainText(), self.mode)
            if not units:
                raise BusinessError("Type the IMEI of at least one phone")
            if self.checker:
                self.checker(units)
        except BusinessError as exc:
            self.status.setStyleSheet("color: #DC2626; font-weight: 600;")
            self.status.setText(str(exc))
            return
        self.value = units
        self.accept()


def ask_sale_imei(parent, product_name, mode, checker=None, title="Enter IMEI"):
    """Returns (imei1, imei2 or None) or None when cancelled."""
    dlg = SaleImeiDialog(parent, product_name, mode, checker, title)
    return dlg.value if dlg.exec() else None


def ask_purchase_imeis(parent, product_name, mode, checker=None):
    """Returns a list of (imei1, imei2 or None) or None when cancelled."""
    dlg = PurchaseImeiDialog(parent, product_name, mode, checker)
    return dlg.value if dlg.exec() else None
