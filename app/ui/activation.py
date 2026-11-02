"""Activation screen: shows this computer's Machine Code and asks for the Activation Key."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton,
                               QVBoxLayout)

from ..config import APP_NAME, DEVELOPER_NAME, DEVELOPER_PHONE
from ..services import licensing


class ActivationDialog(QDialog):
    def __init__(self, data_dir, reason="", parent=None):
        super().__init__(parent)
        self.data_dir = data_dir
        self.setWindowTitle(f"{APP_NAME} - Activation")
        self.setMinimumWidth(560)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(8)
        title = QLabel("Activate your software")
        title.setStyleSheet("font-size: 22px; font-weight: 800;")
        lay.addWidget(title)
        if reason:
            r = QLabel(reason)
            r.setObjectName("error")
            r.setWordWrap(True)
            lay.addWidget(r)
        steps = QLabel(f"1. Send the <b>Machine Code</b> below to <b>{DEVELOPER_NAME}</b> "
                       f"(mobile / WhatsApp: <b>{DEVELOPER_PHONE}</b>).<br>"
                       "2. You will receive an <b>Activation Key</b>. Paste it here and press Activate.")
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
        lay.addWidget(QLabel("Activation Key:"))
        self.key = QPlainTextEdit()
        self.key.setFixedHeight(90)
        self.key.setPlaceholderText("Paste the Activation Key here")
        lay.addWidget(self.key)
        self.error = QLabel("")
        self.error.setObjectName("error")
        self.error.setWordWrap(True)
        lay.addWidget(self.error)
        btns = QHBoxLayout()
        quit_ = QPushButton("Exit")
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
            self.accept()
        else:
            self.error.setText(msg)
