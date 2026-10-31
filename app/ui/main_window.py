"""Temporary main window - replaced by the full home screen + menus in Step 3."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QMainWindow

from ..services import masters


class MainWindow(QMainWindow):
    def __init__(self, db):
        super().__init__()
        self.db = db
        company = masters.get_company(db)
        self.setWindowTitle(company["name"])
        label = QLabel(f"Welcome to {company['name'].upper()}\n(Home screen comes in Step 3)",
                       alignment=Qt.AlignCenter)
        self.setCentralWidget(label)
        self.resize(900, 600)

    def closeEvent(self, event):
        self.db.close()  # writes the final encrypted snapshot
        super().closeEvent(event)
