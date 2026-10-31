"""First-run registration screen."""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QVBoxLayout)

from ..services import auth
from ..services.common import BusinessError


class RegistrationDialog(QDialog):
    def __init__(self, data_dir: Path, parent=None):
        super().__init__(parent)
        self.data_dir = Path(data_dir)
        self.db = None  # set after successful registration
        self.logo_file = None
        self.setWindowTitle("Business Manager - Registration")
        self.setMinimumWidth(480)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(36, 28, 36, 28)
        lay.setSpacing(12)
        title = QLabel("Welcome! Register your company", alignment=Qt.AlignCenter)
        title.setObjectName("title")
        lay.addWidget(title)
        sub = QLabel("This information is saved on this computer only.", alignment=Qt.AlignCenter)
        sub.setObjectName("subtitle")
        lay.addWidget(sub)

        form = QFormLayout()
        form.setVerticalSpacing(10)
        self.name = QLineEdit()
        self.address = QLineEdit()
        self.phone = QLineEdit(placeholderText="03xx-xxxxxxx")
        self.email = QLineEdit(placeholderText="name@example.com")
        self.login_id = QLineEdit()
        self.password = QLineEdit()
        self.confirm = QLineEdit()
        for w in (self.password, self.confirm):
            w.setEchoMode(QLineEdit.Password)
        form.addRow("Company Name *", self.name)
        form.addRow("Address *", self.address)
        form.addRow("Phone Number *", self.phone)
        form.addRow("Email *", self.email)

        logo_row = QHBoxLayout()
        self.preview = QLabel("No logo", alignment=Qt.AlignCenter)
        self.preview.setFixedSize(96, 96)
        self.preview.setStyleSheet("border: 1px dashed #b8c0cc; border-radius: 10px; color: #6b7280;")
        pick = QPushButton("Choose Logo (PNG/JPG)")
        pick.setObjectName("secondary")
        pick.clicked.connect(self.choose_logo)
        logo_row.addWidget(self.preview)
        logo_row.addWidget(pick)
        logo_row.addStretch()
        form.addRow("Company Logo *", logo_row)
        form.addRow("Login ID *", self.login_id)
        form.addRow("Password *", self.password)
        form.addRow("Confirm Password *", self.confirm)
        lay.addLayout(form)

        self.error = QLabel("")
        self.error.setObjectName("error")
        self.error.setWordWrap(True)
        lay.addWidget(self.error)

        save = QPushButton("Save && Continue")
        save.setDefault(True)
        save.clicked.connect(self.save)
        lay.addWidget(save)

    def choose_logo(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select company logo", "",
                                              "Images (*.png *.jpg *.jpeg)")
        if not path:
            return
        pm = QPixmap(path)
        if pm.isNull():
            self.error.setText("That file is not a valid image.")
            return
        self.logo_file = path
        self.preview.setText("")
        self.preview.setPixmap(pm.scaled(90, 90, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.error.setText("")

    def save(self):
        self.error.setText("")
        if not self.logo_file:
            self.error.setText("Company Logo is required")
            return
        try:
            self.db = auth.register(self.data_dir, self.name.text(), self.address.text(),
                                    self.phone.text(), self.email.text(), self.logo_file,
                                    self.login_id.text(), self.password.text(), self.confirm.text())
        except BusinessError as exc:
            self.error.setText(str(exc))
            return
        self.accept()
