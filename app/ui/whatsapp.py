"""Open a WhatsApp chat with the message already typed (the person only presses Send)."""
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMessageBox

from ..services import reminders


def send_whatsapp(parent, phone, text) -> bool:
    if not reminders.normalize_phone(phone):
        QMessageBox.information(parent, "WhatsApp", "This customer has no phone number saved.")
        return False
    if not text:
        QMessageBox.information(parent, "WhatsApp", "There is nothing to remind this customer about.")
        return False
    QDesktopServices.openUrl(QUrl(reminders.whatsapp_url(phone, text)))     # needs WhatsApp / internet on this PC
    return True
