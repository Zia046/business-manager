"""A dialog where the Enter key can never close the window.

Enter either 'clicks' the button that has the focus, or moves to the next field.
(Normal dialogs treat Enter as 'press the default button', which closed the Sale Invoice window.)
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractButton, QDialog, QPlainTextEdit, QPushButton, QTextEdit


class EnterSafeDialog(QDialog):
    escape_closes = True        # data-entry forms set False: Esc must not throw away what was typed
    def showEvent(self, event):
        for b in self.findChildren(QPushButton):
            b.setAutoDefault(False)
            b.setDefault(False)
        super().showEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            w = self.focusWidget()
            if isinstance(w, QAbstractButton):
                w.click()
            elif not isinstance(w, (QPlainTextEdit, QTextEdit)):
                self.focusNextChild()
            event.accept()
            return
        if event.key() == Qt.Key_Escape and not self.escape_closes:
            event.accept()                      # close with the Cancel / Close button (or the window's X)
            return
        super().keyPressEvent(event)
