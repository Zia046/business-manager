"""Maps a menu/button key to the code that opens that screen.

Later steps add entries here; anything not registered shows a placeholder.
"""
from PySide6.QtWidgets import QMessageBox

from ..config import APP_NAME
from . import dialogs


def _company_edit(win):
    if dialogs.CompanyEditDialog(win.db, win).exec():
        win.refresh_header()


def _change_password(win):
    dialogs.ChangePasswordDialog(win.db, win).exec()


MODULES = {
    "company_edit": _company_edit,
    "about": lambda win: dialogs.show_about(win, win.db),
    "change_password": _change_password,
}


def open_module(win, key: str, label: str):
    handler = MODULES.get(key)
    if handler:
        handler(win)
    else:
        QMessageBox.information(win, APP_NAME, f"'{label}' will be available in the next build step.")
