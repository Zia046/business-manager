"""Utilities > Reset Database: choose what to erase, give a reason, current password, 2 confirmations."""
from PySide6.QtWidgets import (QApplication, QCheckBox, QDialog, QLabel, QLineEdit, QMessageBox, QPushButton,
                               QVBoxLayout)

from ..config import APP_NAME
from ..services import reset
from ..services.common import BusinessError
from .enter_safe import EnterSafeDialog


class ResetDialog(EnterSafeDialog):
    def __init__(self, win, parent=None):
        super().__init__(parent or win)
        self.win, self.db = win, win.db
        self.setWindowTitle("Reset Database")
        self.setMinimumWidth(560)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        warn = QLabel("<b style='color:#DC2626'>Warning:</b> erased data cannot be brought back, except from "
                      "the safety backup that is made automatically just before the reset.")
        warn.setWordWrap(True)
        lay.addWidget(warn)
        lay.addWidget(QLabel("<b>What do you want to erase?</b>"))
        self.boxes = {}
        for key, text in reset.OPTIONS.items():
            cb = QCheckBox(text)
            cb.setStyleSheet("QCheckBox { padding: 3px; }")
            cb.toggled.connect(self._sync)
            self.boxes[key] = cb
            lay.addWidget(cb)
        self.note = QLabel("")
        self.note.setObjectName("subtitle")
        self.note.setWordWrap(True)
        lay.addWidget(self.note)
        lay.addWidget(QLabel("Reason for reset *"))
        self.reason = QLineEdit(placeholderText="Why are you resetting? (written in the reset log)")
        lay.addWidget(self.reason)
        lay.addWidget(QLabel("Current password *"))
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        lay.addWidget(self.password)
        self.error = QLabel("")
        self.error.setObjectName("error")
        self.error.setWordWrap(True)
        lay.addWidget(self.error)
        go = QPushButton("Erase Selected Data")
        go.setObjectName("danger")
        go.setStyleSheet("background:#DC2626; color:white; font-weight:700; padding:8px;")
        go.clicked.connect(self.run)
        cancel = QPushButton("Cancel")
        cancel.setObjectName("secondary")
        cancel.clicked.connect(self.reject)
        lay.addWidget(go)
        lay.addWidget(cancel)
        self._syncing = False

    def _selected(self):
        return [k for k, cb in self.boxes.items() if cb.isChecked()]

    def _sync(self, *_):
        if getattr(self, "_syncing", False):
            return
        self._syncing = True
        chosen = self._selected()
        try:
            full = reset.expand(chosen) if chosen else set()
        except BusinessError:
            full = set()
        factory = "factory" in chosen
        for key, cb in self.boxes.items():
            if factory and key != "factory":
                cb.setChecked(True)
                cb.setEnabled(False)
            else:
                cb.setEnabled(True)
        if not factory:
            if "transactions" in full and "transactions" not in chosen:
                self.boxes["transactions"].setChecked(True)
        self.note.setText("Transactions will also be erased because the chosen data depends on them."
                          if full - set(chosen) and not factory else "")
        self._syncing = False

    def run(self):
        self.error.setText("")
        chosen = self._selected()
        if not chosen:
            self.error.setText("Select what you want to erase.")
            return
        if len(self.reason.text().strip()) < 5:
            self.error.setText("Write the reason for the reset (at least 5 letters).")
            return
        if not self.password.text():
            self.error.setText("Enter your current password.")
            return
        names = "\n".join("  - " + reset.OPTIONS[k].split(":")[0].split(" (")[0] for k in chosen)
        no = QMessageBox.No
        if QMessageBox.warning(self, "Confirm 1 of 2", f"You are about to erase:\n{names}\n\nContinue?",
                               QMessageBox.Yes | QMessageBox.No, no) != QMessageBox.Yes:
            return
        if QMessageBox.critical(self, "Confirm 2 of 2 - FINAL",
                                "This is the final confirmation.\nThe data will be erased now.\n\nAre you sure?",
                                QMessageBox.Yes | QMessageBox.No, no) != QMessageBox.Yes:
            return
        try:
            res = reset.reset_data(self.db, self.password.text(), self.reason.text(), chosen)
        except BusinessError as exc:
            self.error.setText(str(exc))
            return
        if res["factory"]:
            QMessageBox.information(self, APP_NAME, "Everything was erased. The software will close now; "
                                    "open it again to register.\n\nSafety backup: " + res["safety"].name)
            self.win.skip_exit_backup = True
            QApplication.quit()
            return
        QMessageBox.information(self, APP_NAME, "Selected data was erased.\n\nSafety backup: " + res["safety"].name)
        self.accept()
        self.win.refresh_header()
