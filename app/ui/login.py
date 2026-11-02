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
        self.db = None  # set on successful login (db.user = who logged in)
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

        remembered = brand.get("login_id")
        self.login_id = QLineEdit(remembered or "", placeholderText="Login ID")
        self.password = QLineEdit(placeholderText="Password")
        self.password.setEchoMode(QLineEdit.Password)
        if remembered:
            # the Login ID is remembered: only the password is asked each time
            self.who = QLabel(f"Login ID:  <b>{remembered}</b>", alignment=Qt.AlignCenter)
            lay.addWidget(self.who)
            self.login_id.hide()
            self.other = QPushButton("Login with a different Login ID")
            self.other.setObjectName("secondary")
            self.other.setFlat(True)
            self.other.setAutoDefault(False)
            self.other.clicked.connect(self._show_login_id)
            lay.addWidget(self.login_id)
            lay.addWidget(self.password)
            lay.addWidget(self.other)
        else:
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
        (self.password if remembered else self.login_id).setFocus()

    def _show_login_id(self):
        self.who.hide()
        self.other.hide()
        self.login_id.show()
        self.login_id.selectAll()
        self.login_id.setFocus()

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
