"""Outstanding SMS Template Settings: the message the Android Companion app sends, and the business's own
payment details. The same message is shown and edited on the phone; the newest saved version wins."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit,
                               QPushButton, QVBoxLayout)

from ..services import reports, sms_template
from ..services.common import BusinessError
from .theme import C_RED

FIELD_LABELS = (("business_name", "Business Name"), ("contact", "Business Contact Number"),
                ("account_name", "Payment Account Name"), ("easypaisa", "Easypaisa Number"),
                ("jazzcash", "JazzCash Number"), ("other", "Other Payment Instructions"))


class MobileReminderDialog(QDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.version = 0
        self.setWindowTitle("Outstanding SMS Template Settings")
        self.resize(980, 640)
        root = QHBoxLayout(self)

        left = QVBoxLayout()
        left.addWidget(QLabel("<b style='font-size:15px'>Message</b>"))
        help_ = QLabel(sms_template.INSTRUCTIONS_UR)
        help_.setWordWrap(True)
        help_.setLayoutDirection(Qt.RightToLeft)
        help_.setStyleSheet("background: #FFF7E0; border: 1px solid #E8C766; border-radius: 8px; padding: 8px; "
                            "font-size: 14px;")
        left.addWidget(help_)
        left.addWidget(QLabel("Write <b>****</b> (four stars) where the customer's outstanding amount should appear."))
        self.edit = QPlainTextEdit()
        self.edit.textChanged.connect(self._check)
        left.addWidget(self.edit, 1)
        self.state = QLabel("")
        self.state.setWordWrap(True)
        left.addWidget(self.state)
        self.info = QLabel("")
        self.info.setObjectName("subtitle")
        self.info.setWordWrap(True)
        left.addWidget(self.info)
        row = QHBoxLayout()
        for text, fn, secondary in (("Restore Default Template", self._restore, True),
                                    ("Preview Message", self._preview, True), ("Save Template", self._save, False)):
            b = QPushButton(text)
            b.setAutoDefault(False)
            if secondary:
                b.setObjectName("secondary")
            b.clicked.connect(fn)
            row.addWidget(b)
        left.addLayout(row)
        root.addLayout(left, 3)

        right = QVBoxLayout()
        right.addWidget(QLabel("<b style='font-size:15px'>Business and payment details</b>"))
        note = QLabel("These belong to this business only. The default message is built from them.")
        note.setObjectName("subtitle")
        note.setWordWrap(True)
        right.addWidget(note)
        form = QFormLayout()
        self.fields = {}
        for key, label in FIELD_LABELS:
            self.fields[key] = QLineEdit()
            form.addRow(label, self.fields[key])
        right.addLayout(form)
        save_b = QPushButton("Save Business Details")
        save_b.setAutoDefault(False)
        save_b.clicked.connect(self._save_business)
        right.addWidget(save_b)
        right.addStretch(1)
        close = QPushButton("Close")
        close.setObjectName("secondary")
        close.setAutoDefault(False)
        close.clicked.connect(self.reject)
        right.addWidget(close)
        root.addLayout(right, 2)
        self._load()

    def _load(self):
        cur = sms_template.current(self.db)
        self.version = cur["version"]
        self.edit.setPlainText(cur["text"])
        self.info.setText("Standard message (not edited yet)." if not cur["version"] else
                          f"Version {cur['version']}  |  saved {cur['updated_at']}  |  by {cur['updated_by']}")
        biz = sms_template.business(self.db)
        for key, _ in FIELD_LABELS:
            self.fields[key].setText(biz[key])

    def _text(self):
        return self.edit.toPlainText().strip()

    def _check(self):
        n = sms_template.count_slots(self._text())
        if n == 0:
            self.state.setText(f"<span style='color:{C_RED}'><b>**** is missing.</b> Write exactly four stars "
                               "where the outstanding amount should appear.</span>")
        else:
            chars = len(sms_template.render(self._text(), 12500))
            self.state.setText(f"**** found {n} time(s). About {chars} characters; an Urdu SMS is sent as "
                               f"{max(1, -(-chars // 67))} part(s).")

    def _sample(self):
        rows = reports.outstanding(self.db)
        people = rows["customers"] + rows["loans"]
        people = [p for p in people if p["balance"] > 0]
        return (people[0]["name"], people[0]["balance"]) if people else ("example amount", 12500)

    def _preview(self):
        try:
            text = sms_template.check(self._text())
        except BusinessError as exc:
            QMessageBox.warning(self, "Message", str(exc))
            return
        name, amount = self._sample()
        QMessageBox.information(self, f"Preview ({name})", sms_template.render(text, amount))

    def _save(self):
        try:
            sms_template.save(self.db, self._text(), self.version)
        except sms_template.TemplateConflict as exc:
            QMessageBox.warning(self, "Message", str(exc))
            self._load()
            return
        except BusinessError as exc:
            QMessageBox.warning(self, "Message", str(exc))
            return
        self._load()
        QMessageBox.information(self, "Saved", "Saved. The Android app gets this message at its next sync.")

    def _restore(self):
        if QMessageBox.question(self, "Restore", "Replace your message with the standard message?") != QMessageBox.Yes:
            return
        try:
            sms_template.restore_default(self.db, self.version)
        except BusinessError as exc:
            QMessageBox.warning(self, "Message", str(exc))
        self._load()

    def _save_business(self):
        try:
            sms_template.save_business(self.db, **{k: w.text() for k, w in self.fields.items()})
        except BusinessError as exc:
            QMessageBox.warning(self, "Business details", str(exc))
            return
        QMessageBox.information(self, "Saved", "Saved. Press 'Restore Default Template' if you want the standard "
                                "message to be written again with these details.")
