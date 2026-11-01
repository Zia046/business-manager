"""Business Manager entry point:  python main.py"""
import sys

from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from app.config import APP_NAME, resolve_data_dir
from app.services import auth
from app.ui.login import LoginDialog
from app.ui.main_window import MainWindow
from app.ui.registration import RegistrationDialog
from app.ui.theme import STYLESHEET


def _install_crash_logger():
    """The exe has no console, so any unexpected error is written to error_log.txt and shown in a box."""
    import traceback
    from datetime import datetime
    from pathlib import Path

    def hook(exc_type, exc, tb):
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        try:
            data_dir, _ = resolve_data_dir()
            log = Path(data_dir) / "error_log.txt"
            with open(log, "a", encoding="utf-8") as f:
                f.write(f"\n--- {datetime.now():%Y-%m-%d %H:%M:%S} ---\n{text}")
            where = f"\n\nDetails saved in:\n{log}"
        except Exception:
            where = ""
        try:
            QMessageBox.critical(None, APP_NAME, f"Something went wrong:\n\n{exc}{where}")
        except Exception:
            pass
    sys.excepthook = hook


def run() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    _install_crash_logger()
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
