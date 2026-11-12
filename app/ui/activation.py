"""Licence activation: shows the licence status and this computer's Machine Code and asks for the License Key.

Opened by itself when the free trial has ended, and from Utilities > License Activation at any time."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit,
                               QPushButton, QVBoxLayout)

from ..config import APP_NAME, DEVELOPER_NAME, DEVELOPER_PHONE
from ..services import licensing


class ActivationDialog(QDialog):
    def __init__(self, data_dir, reason="", parent=None, from_settings=False):
        super().__init__(parent)
        self.data_dir = data_dir
        self.setWindowTitle(f"{APP_NAME} - License Activation")
        self.setMinimumWidth(560)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(8)
        title = QLabel("Activate your software")
        title.setStyleSheet("font-size: 22px; font-weight: 800;")
        lay.addWidget(title)
        self.status = QLabel()
        self.status.setStyleSheet("font-size: 15px; font-weight: 700;")
        lay.addWidget(self.status)
        self._show_status()
        if reason:
            r = QLabel(reason)
            r.setObjectName("error")
            r.setWordWrap(True)
            lay.addWidget(r)
        steps = QLabel(f"1. Send the <b>Machine Code</b> below to <b>{DEVELOPER_NAME}</b> "
                       f"(mobile / WhatsApp: <b>{DEVELOPER_PHONE}</b>).<br>"
                       "2. You will receive a <b>License Key</b>. Paste it here and press Activate.")
        steps.setWordWrap(True)
        lay.addWidget(steps)
        row = QHBoxLayout()
        self.code = QLineEdit(licensing.machine_code())
        self.code.setReadOnly(True)
        self.code.setStyleSheet("font-size: 20px; font-weight: 700; letter-spacing: 2px;")
        copy = QPushButton("Copy")
        copy.setObjectName("secondary")
        copy.clicked.connect(lambda: QApplication.clipboard().setText(self.code.text()))
        row.addWidget(self.code, 1)
        row.addWidget(copy)
        lay.addLayout(row)
        lay.addWidget(QLabel("License Key:"))
        self.key = QPlainTextEdit()
        self.key.setFixedHeight(90)
        self.key.setPlaceholderText("Paste the License Key here")
        lay.addWidget(self.key)
        self.error = QLabel("")
        self.error.setObjectName("error")
        self.error.setWordWrap(True)
        lay.addWidget(self.error)
        btns = QHBoxLayout()
        quit_ = QPushButton("Close" if from_settings else "Exit")
        quit_.setObjectName("secondary")
        quit_.clicked.connect(self.reject)
        go = QPushButton("Activate")
        go.clicked.connect(self.activate)
        btns.addStretch()
        btns.addWidget(quit_)
        btns.addWidget(go)
        lay.addLayout(btns)

    def activate(self):
        ok, msg = licensing.activate(self.data_dir, self.key.toPlainText())
        if ok:
            self._show_status()
            QMessageBox.information(self, APP_NAME, "Thank you. The software is activated on this computer.")
            self.accept()
        else:
            self.error.setText(msg)

    def _show_status(self):
        st = licensing.overall(self.data_dir)
        self.status.setText(f"License status: {st['label']}")
