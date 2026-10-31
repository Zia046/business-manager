"""Business Manager entry point:  python main.py"""
import sys

from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from app.config import APP_NAME, resolve_data_dir
from app.services import auth
from app.ui.login import LoginDialog
from app.ui.main_window import MainWindow
from app.ui.registration import RegistrationDialog
from app.ui.theme import STYLESHEET


def run() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyleSheet(STYLESHEET)

    data_dir, used_fallback = resolve_data_dir()
    if used_fallback and not auth.is_registered(data_dir):
        QMessageBox.information(None, APP_NAME,
                                f"Drive D: was not found. Data will be saved in:\n{data_dir}")

    if not auth.is_registered(data_dir):
        reg = RegistrationDialog(data_dir)
        if reg.exec() != QDialog.Accepted:
            return 0
        reg.db.close()  # registration done -> go to the login screen

    login = LoginDialog(data_dir)
    if login.exec() != QDialog.Accepted:
        return 0

    window = MainWindow(login.db)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(run())
