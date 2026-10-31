"""Small utility dialogs: company edit, change password, about."""
import shutil
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPushButton, QVBoxLayout)

from ..config import APP_NAME, APP_VERSION
from ..services import auth, masters
from ..services.common import BusinessError


class CompanyEditDialog(QDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Company Information")
        self.setMinimumWidth(460)
        co = masters.get_company(db)
        self.new_logo = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 24)
        form = QFormLayout()
        self.name = QLineEdit(co["name"])
        self.address = QLineEdit(co["address"])
        self.phone = QLineEdit(co["phone"])
        self.email = QLineEdit(co["email"])
        form.addRow("Company Name", self.name)
        form.addRow("Address", self.address)
        form.addRow("Phone Number", self.phone)
        form.addRow("Email", self.email)

        row = QHBoxLayout()
        self.preview = QLabel(alignment=Qt.AlignCenter)
        self.preview.setFixedSize(90, 90)
        if co["logo_path"] and Path(co["logo_path"]).exists():
            self.preview.setPixmap(QPixmap(co["logo_path"]).scaled(84, 84, Qt.KeepAspectRatio,
                                                                    Qt.SmoothTransformation))
        pick = QPushButton("Change Logo")
        pick.setObjectName("secondary")
        pick.clicked.connect(self.choose_logo)
        row.addWidget(self.preview)
        row.addWidget(pick)
        row.addStretch()
        form.addRow("Logo", row)
        lay.addLayout(form)

        self.error = QLabel("")
        self.error.setObjectName("error")
        lay.addWidget(self.error)
        save = QPushButton("Save")
        save.setDefault(True)
        save.clicked.connect(self.save)
        lay.addWidget(save)

    def choose_logo(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select logo", "", "Images (*.png *.jpg *.jpeg)")
        if path and not QPixmap(path).isNull():
            self.new_logo = path
            self.preview.setPixmap(QPixmap(path).scaled(84, 84, Qt.KeepAspectRatio,
                                                         Qt.SmoothTransformation))

    def save(self):
        try:
            logo_dest = None
            if self.new_logo:
                src = Path(self.new_logo)
                logo_dest = str(Path(self.db.data_dir) / "logo" / f"logo{src.suffix.lower()}")
                if src.resolve() != Path(logo_dest).resolve():
                    shutil.copyfile(src, logo_dest)
            masters.update_company(self.db, self.name.text(), self.address.text(),
                                   self.phone.text(), self.email.text(), logo_dest)
        except BusinessError as exc:
            self.error.setText(str(exc))
            return
        self.accept()


class ChangePasswordDialog(QDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Change Password / Username")
        self.setMinimumWidth(400)
        user = db.one("SELECT login_id FROM users LIMIT 1")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 24)
        form = QFormLayout()
        self.current = QLineEdit()
        self.login_id = QLineEdit(user["login_id"])
        self.new_pw = QLineEdit(placeholderText="Leave empty to keep current password")
        self.confirm = QLineEdit()
        for w in (self.current, self.new_pw, self.confirm):
            w.setEchoMode(QLineEdit.Password)
        form.addRow("Current Password *", self.current)
        form.addRow("Login ID", self.login_id)
        form.addRow("New Password", self.new_pw)
        form.addRow("Confirm New Password", self.confirm)
        lay.addLayout(form)

        self.error = QLabel("")
        self.error.setObjectName("error")
        self.error.setWordWrap(True)
        lay.addWidget(self.error)
        save = QPushButton("Update")
        save.setDefault(True)
        save.clicked.connect(self.save)
        lay.addWidget(save)

    def save(self):
        if self.new_pw.text() != self.confirm.text():
            self.error.setText("New passwords do not match")
            return
        try:
            auth.change_credentials(self.db, self.current.text(), self.login_id.text(),
                                    self.new_pw.text() or None)
        except BusinessError as exc:
            self.error.setText(str(exc))
            return
        QMessageBox.information(self, APP_NAME, "Login details updated successfully.")
        self.accept()


def show_about(parent, db):
    co = masters.get_company(db)
    QMessageBox.about(parent, f"About {APP_NAME}",
                      f"<h3>{APP_NAME}</h3>Version {APP_VERSION}<br><br>"
                      f"Licensed to: <b>{co['name']}</b><br>"
                      "Works fully offline. All data is stored encrypted on this computer.")
