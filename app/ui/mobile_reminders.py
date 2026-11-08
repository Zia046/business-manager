"""Outstanding reminders for the phone app: edit the SMS text and export the list of customers as a file."""
import json
from pathlib import Path

from PySide6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit, QPushButton,
                               QVBoxLayout)

from ..services import backup, reminders


class MobileReminderDialog(QDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Reminders for the Mobile App (SMS)")
        self.resize(640, 560)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("<b>Message</b> - write <b>xxxxxx</b> where each customer's balance should come:"))
        self.edit = QPlainTextEdit()
        self.edit.setPlainText(backup.get_settings(db.data_dir).get("sms_template") or reminders.DEFAULT_SMS_TEMPLATE)
        self.edit.textChanged.connect(self._preview)
        lay.addWidget(self.edit, 1)
        self.preview = QLabel("")
        self.preview.setWordWrap(True)
        self.preview.setObjectName("subtitle")
        lay.addWidget(self.preview)
        self.info = QLabel("")
        self.info.setWordWrap(True)
        lay.addWidget(self.info)
        row = QHBoxLayout()
        reset = QPushButton("Original Message")
        reset.setObjectName("secondary")
        reset.clicked.connect(lambda: self.edit.setPlainText(reminders.DEFAULT_SMS_TEMPLATE))
        go = QPushButton("Save Message && Export File")
        go.clicked.connect(self._export)
        close = QPushButton("Close")
        close.setObjectName("secondary")
        close.clicked.connect(self.reject)
        row.addWidget(reset)
        row.addStretch()
        row.addWidget(go)
        row.addWidget(close)
        lay.addLayout(row)
        self._preview()

    def _template(self):
        return self.edit.toPlainText().strip()

    def _preview(self):
        data = reminders.mobile_export(self.db, self._template() or None)
        n = len(data["items"])
        self.info.setText(f"{n} customer(s) with a balance and a phone number will be exported"
                          + (f"  ({data['no_phone']} more have no phone number saved)." if data["no_phone"] else "."))
        t = self._template()
        if reminders.SMS_PLACEHOLDER not in t:
            self.preview.setText("<span style='color:#DC2626'>The message must contain xxxxxx "
                                 "(it becomes the balance).</span>")
        else:
            n_chars = len(reminders.sms_text(t, 12500))
            self.preview.setText(f"About {n_chars} characters. Urdu SMS use the Unicode format, so the phone sends it as "
                                 f"{max(1, -(-n_chars // 67))} message part(s) per customer.")

    def _export(self):
        t = self._template()
        if reminders.SMS_PLACEHOLDER not in t:
            QMessageBox.warning(self, "Message", "Write xxxxxx where the balance should come.")
            return
        backup.save_settings(self.db.data_dir, sms_template=t)
        data = reminders.mobile_export(self.db, t)
        if not data["items"]:
            QMessageBox.information(self, "Reminders", "No customer with a balance and a phone number.")
            return
        default = str(Path(self.db.data_dir) / "reminders.json")
        path, _ = QFileDialog.getSaveFileName(self, "Save the reminders file", default, "Reminders (*.json)")
        if not path:
            return
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        QMessageBox.information(self, "Saved", f"{len(data['items'])} customer(s) saved in:\n{path}\n\n"
                                "Send this file to your phone (WhatsApp, Bluetooth, USB cable or Google Drive), "
                                "then open the 'Burhan Reminder' app and press 'Open reminders file'.")
