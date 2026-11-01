"""Home screen: live date/time, logo + company NAME, 7 big buttons and the top menu bar."""
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (QGridLayout, QHBoxLayout, QLabel, QMainWindow, QPushButton,
                               QVBoxLayout, QWidget)

from ..services import backup, masters
from .menu_spec import HOME_BUTTONS, MENUS, SHORTCUTS
from .modules import open_module
from .theme import ACCENT, BG, HOME_BTN_BG, HOME_BTN_BORDER, HOME_BTN_HOVER, HOME_BTN_TEXT, MUTED

HOME_BUTTON_STYLE = f"""
QPushButton {{ background: {HOME_BTN_BG}; color: {HOME_BTN_TEXT}; border: 1px solid {HOME_BTN_BORDER};
              border-radius: 14px; padding: 18px 12px; font-size: 16px; font-weight: 600;
              min-width: 190px; min-height: 64px; }}
QPushButton:hover {{ background: {HOME_BTN_HOVER}; border: 1px solid #e58f8a; }}
"""


class MainWindow(QMainWindow):
    def __init__(self, db):
        super().__init__()
        self.db = db
        self.skip_exit_backup = False
        self.setStyleSheet(f"QMainWindow, QWidget#home {{ background: {BG}; }}")
        self._build_menu()
        QShortcut(QKeySequence("F2"), self, activated=lambda: open_module(self, "sale_invoice", "Sale Invoice"))
        self._build_home()
        self.refresh_header()
        self._tick()
        timer = QTimer(self)  # live clock, updates every second
        timer.timeout.connect(self._tick)
        timer.start(1000)
        self.resize(1000, 700)

    # ---------- menu bar ----------
    def _build_menu(self):
        bar = self.menuBar()
        for title, items in MENUS:
            menu = bar.addMenu(title)
            for label, key in items:
                act = QAction(label, self)
                act.triggered.connect(lambda _=False, k=key, l=label: open_module(self, k, l))
                if key in SHORTCUTS and title in ("Sale/Purchase", "Payments/Receipts"):
                    act.setShortcut(QKeySequence(SHORTCUTS[key]))
                menu.addAction(act)

    # ---------- home page ----------
    def _build_home(self):
        home = QWidget(objectName="home")
        self.setCentralWidget(home)
        root = QVBoxLayout(home)
        root.setContentsMargins(40, 18, 40, 30)

        top = QHBoxLayout()
        top.addStretch()
        self.clock = QLabel(alignment=Qt.AlignRight)
        self.clock.setStyleSheet(f"color: {MUTED}; font-size: 15px; font-weight: 600;")
        top.addWidget(self.clock)
        root.addLayout(top)
        root.addStretch(1)

        self.logo = QLabel(alignment=Qt.AlignCenter)
        root.addWidget(self.logo)
        self.name = QLabel(alignment=Qt.AlignCenter)
        self.name.setStyleSheet("font-size: 30px; font-weight: 800; letter-spacing: 2px;")
        self.name.setWordWrap(True)
        root.addWidget(self.name)
        root.addSpacing(26)

        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(18)
        for i, (label, key) in enumerate(HOME_BUTTONS):
            btn = QPushButton(f"{i + 1}.  {label}")
            btn.setStyleSheet(HOME_BUTTON_STYLE)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, k=key, l=label: open_module(self, k, l))
            grid.addWidget(btn, i // 4, i % 4)
        grid_wrap = QHBoxLayout()
        grid_wrap.addStretch()
        grid_wrap.addLayout(grid)
        grid_wrap.addStretch()
        root.addLayout(grid_wrap)
        root.addStretch(2)

    def refresh_header(self):
        """Reload company name (CAPITAL LETTERS) and logo, e.g. after Company Information Edit."""
        co = masters.get_company(self.db)
        self.setWindowTitle(co["name"])
        self.name.setText(co["name"].upper())
        if co["logo_path"] and Path(co["logo_path"]).exists():
            self.logo.setPixmap(QPixmap(co["logo_path"]).scaled(150, 150, Qt.KeepAspectRatio,
                                                                Qt.SmoothTransformation))
        else:
            self.logo.clear()

    def _tick(self):
        self.clock.setText(datetime.now().strftime("%A, %d %B %Y     %I:%M:%S %p"))

    def closeEvent(self, event):
        if not self.skip_exit_backup and self.db.conn is not None:
            backup.auto_backup_on_exit(self.db)   # never blocks closing, even if it fails
        self.db.close()  # writes the final encrypted snapshot (no-op after a restore)
        super().closeEvent(event)
