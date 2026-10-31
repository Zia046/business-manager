"""Login screen (shown on every launch after registration)."""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QDialog, QLabel, QLineEdit, QPushButton, QVBoxLayout)

from ..services import auth
from ..services.common import BusinessError


class LoginDialog(QDialog):
    def __init__(self, data_dir: Path, parent=None):
        super().__init__(parent)
        self.data_dir = Path(data_dir)
        self.db = None  # set on successful login
        self.setWindowTitle("Login")
        self.setFixedWidth(400)

        brand = auth.read_branding(self.data_dir)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(36, 30, 36, 30)
        lay.setSpacing(12)

        logo = QLabel(alignment=Qt.AlignCenter)
        if brand.get("logo") and Path(brand["logo"]).exists():
            logo.setPixmap(QPixmap(brand["logo"]).scaled(110, 110, Qt.KeepAspectRatio,
                                                         Qt.SmoothTransformation))
        lay.addWidget(logo)
        title = QLabel((brand.get("name") or "").upper(), alignment=Qt.AlignCenter)
        title.setObjectName("title")
        title.setWordWrap(True)
        lay.addWidget(title)
        sub = QLabel("Please login to continue", alignment=Qt.AlignCenter)
        sub.setObjectName("subtitle")
        lay.addWidget(sub)

        self.login_id = QLineEdit(placeholderText="Login ID")
        self.password = QLineEdit(placeholderText="Password")
        self.password.setEchoMode(QLineEdit.Password)
        lay.addWidget(self.login_id)
        lay.addWidget(self.password)

        self.error = QLabel("", alignment=Qt.AlignCenter)
        self.error.setObjectName("error")
        self.error.setWordWrap(True)
        lay.addWidget(self.error)

        self.btn = QPushButton("Login")
        self.btn.setDefault(True)  # Enter key submits
        self.btn.clicked.connect(self.try_login)
        lay.addWidget(self.btn)
        self.login_id.returnPressed.connect(self.password.setFocus)
        self.password.returnPressed.connect(self.try_login)

    def try_login(self):
        self.error.setText("")
        try:
            self.db = auth.login(self.data_dir, self.login_id.text(), self.password.text())
        except BusinessError as exc:
            self.error.setText(str(exc))  # "Invalid Login ID or Password" / lockout message
            self.password.clear()
            self.password.setFocus()
            return
        self.accept()
