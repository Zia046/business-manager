"""Home screen: live date/time, logo + company NAME, 7 big buttons and the top menu bar."""
from datetime import datetime
from pathlib import Path

import time

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (QApplication, QGridLayout, QHBoxLayout, QLabel, QMainWindow, QPushButton,
                               QStackedWidget, QVBoxLayout, QWidget)

from ..config import DEVELOPER_EMAIL, DEVELOPER_NAME, DEVELOPER_PHONE
from ..services import backup, masters, reports as R
from ..services import permissions
from .dashboard import DashboardPage
from .menu_spec import HOME_BUTTONS, MENUS, SHORTCUTS
from .modules import open_module
from .theme import ACCENT, BG, HOME_BTN_BG, HOME_BTN_BORDER, HOME_BTN_HOVER, HOME_BTN_TEXT, MUTED

IDLE_SECONDS = 90          # after this long without use, the Dashboard is shown

HOME_BUTTON_STYLE = f"""
QPushButton {{ background: {HOME_BTN_BG}; color: {HOME_BTN_TEXT}; border: 1px solid {HOME_BTN_BORDER};
              border-radius: 14px; padding: 18px 12px; font-size: 16px; font-weight: 600;
              min-width: 190px; min-height: 64px; }}
QPushButton:hover {{ background: {HOME_BTN_HOVER}; border: 1px solid #e58f8a; }}
"""


class MainWindow(QMainWindow):
    def __init__(self, db, user=None):
        super().__init__()
        self.db = db
        self.user = user or {"login_id": "", "role": "owner", "name": ""}
        self.skip_exit_backup = False
        self.setStyleSheet(f"QMainWindow, QWidget#home {{ background: {BG}; }}")
        self._build_menu()
        QShortcut(QKeySequence("F2"), self, activated=lambda: open_module(self, "sale_invoice", "Sale Invoice"))
        QShortcut(QKeySequence("F5"), self, activated=self.show_dashboard)
        # pages: Home (7 buttons) and Dashboard; the developer line below them is always visible
        self.stack = QStackedWidget()
        container = QWidget(objectName="home")
        cl = QVBoxLayout(container)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        cl.addWidget(self.stack, 1)
        cl.addWidget(self._build_footer())
        self.setCentralWidget(container)
        self._build_home()
        self.dashboard = DashboardPage(self.db, self.user)
        self.dashboard.home_requested.connect(self.show_home)
        self.stack.addWidget(self.dashboard)
        self._last_activity = time.time()
        QApplication.instance().installEventFilter(self)       # to know when nobody is using the program
        idle = QTimer(self)
        idle.timeout.connect(self._idle_check)
        idle.start(10000)
        self.refresh_header()
        self.refresh_dashboard()
        dash = QTimer(self)
        dash.timeout.connect(self.refresh_dashboard)
        dash.start(20000)
        auto = QTimer(self)                          # backup while working, not only when closing
        auto.timeout.connect(lambda: backup.periodic_backup(self.db))
        auto.start(10 * 60 * 1000)
        self._tick()
        timer = QTimer(self)  # live clock, updates every second
        timer.timeout.connect(self._tick)
        timer.start(1000)
        self.resize(1200, 740)

    # ---------- menu bar ----------
    def _build_menu(self):
        bar = self.menuBar()
        for text, fn in (("Dashboard", self.show_dashboard), ("Home", self.show_home)):
            act = QAction(text, self)
            act.triggered.connect(lambda _=False, f=fn: f())
            bar.addAction(act)
        for title, items in MENUS:
            menu = bar.addMenu(title)
            for label, key in items:
                act = QAction(label, self)
                act.triggered.connect(lambda _=False, k=key, l=label: open_module(self, k, l))
                if not permissions.can_open(self.user["role"], key):
                    act.setEnabled(False)                      # staff: owner-only items are greyed out
                if key in SHORTCUTS and title in ("Sale/Purchase", "Payments/Receipts"):
                    act.setShortcut(QKeySequence(SHORTCUTS[key]))
                menu.addAction(act)

    # ---------- home page ----------
    def _build_home(self):
        home = QWidget(objectName="home")
        self.stack.addWidget(home)
        self.home_page = home
        root = QVBoxLayout(home)
        root.setContentsMargins(40, 18, 40, 30)

        top = QHBoxLayout()
        who = QLabel(f"Logged in: <b>{self.user.get('name') or self.user['login_id']}</b> "
                     f"({self.user['role']})" if self.user["login_id"] else "")
        who.setStyleSheet(f"color: {MUTED}; font-size: 13px;")
        top.addWidget(who)
        dash_btn = QPushButton("Dashboard")
        dash_btn.setObjectName("secondary")
        dash_btn.clicked.connect(self.show_dashboard)
        top.addWidget(dash_btn)
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
            btn.setEnabled(permissions.can_open(self.user["role"], key))
            btn.clicked.connect(lambda _=False, k=key, l=label: (open_module(self, k, l), self.refresh_dashboard()))
            grid.addWidget(btn, i // 4, i % 4)
        grid_wrap = QHBoxLayout()
        grid_wrap.addStretch()
        grid_wrap.addLayout(grid)
        grid_wrap.addStretch()
        root.addLayout(grid_wrap)
        root.addSpacing(22)

        # ---- today at a glance ----
        cards = QHBoxLayout()
        cards.addStretch()
        self.cards = {}
        owner_only = {"cash", "receivable", "last_backup"}
        for key, title in (("today_sales", "Today's Sale"), ("cash", "Cash in Hand"),
                           ("receivable", "Customers Owe You"), ("low_stock", "Low-stock Items"),
                           ("phones_in_stock", "Phones in Stock"), ("qist_overdue", "Qist Overdue"),
                           ("last_backup", "Last Backup")):
            if key in owner_only and self.user["role"] != "owner":
                continue                                     # staff do not see money totals or backup state
            box = QLabel(alignment=Qt.AlignCenter)
            box.setMinimumWidth(128)
            box.setStyleSheet("background: white; border: 1px solid #c9d6e8; border-radius: 10px; padding: 8px;")
            cards.addWidget(box)
            self.cards[key] = (box, title)
        cards.addStretch()
        root.addLayout(cards)
        root.addStretch(2)

    def _build_footer(self):
        """Fixed developer line: a plain label (no input), so it can be neither edited nor deleted."""
        dev = QLabel(f"Developed by <b>{DEVELOPER_NAME}</b>   |   Mobile: <b>{DEVELOPER_PHONE}</b>   |   "
                     f"Email: <b>{DEVELOPER_EMAIL}</b>", alignment=Qt.AlignCenter)
        dev.setStyleSheet(f"color: {MUTED}; font-size: 13px; padding: 6px;")
        dev.setFocusPolicy(Qt.NoFocus)
        dev.setTextInteractionFlags(Qt.NoTextInteraction)
        return dev

    # ---------- pages ----------
    def show_dashboard(self):
        self.dashboard.refresh()
        self.stack.setCurrentWidget(self.dashboard)

    def show_home(self):
        self.stack.setCurrentWidget(self.home_page)

    def eventFilter(self, obj, ev):
        if ev.type() in (QEvent.MouseMove, QEvent.MouseButtonPress, QEvent.KeyPress, QEvent.Wheel):
            self._last_activity = time.time()
        return super().eventFilter(obj, ev)

    def _idle_check(self):
        """Nobody is working: leave the Dashboard on the screen (never interrupts an open window)."""
        if (self.stack.currentWidget() is self.home_page and time.time() - self._last_activity > IDLE_SECONDS
                and QApplication.activeModalWidget() is None and not getattr(self, "invoice_windows", [])):
            self.show_dashboard()

    def refresh_dashboard(self):
        try:
            d = R.dashboard(self.db)
        except Exception:
            return                                   # never let a card problem stop the program
        vals = {"today_sales": f"{d['today_sales']:,.0f}  ({d['today_invoices']} bills)", "cash": f"{d['cash']:,.0f}",
                "receivable": f"{d['receivable']:,.0f}", "low_stock": str(d["low_stock"]),
                "phones_in_stock": str(d["phones_in_stock"]), "qist_overdue": str(d["qist_overdue"])}
        info = backup.last_backup_info(self.db.data_dir)
        hours = info["age_hours"]
        vals["last_backup"] = ("Never!" if hours is None else "Just now" if hours < 1 else
                               f"{hours:.0f} hours ago" if hours < 48 else f"{hours / 24:.0f} days ago")
        if self.stack.currentWidget() is self.dashboard:
            self.dashboard.refresh()
        for key, (box, title) in self.cards.items():
            red = (key == "low_stock" and d["low_stock"] > 0) or (key == "qist_overdue" and d["qist_overdue"] > 0) \
                or (key == "last_backup" and (hours is None or hours > 48))
            box.setText(f"<span style='color:#6b7280;font-size:12px'>{title}</span><br>"
                        f"<span style='font-size:18px;font-weight:700;color:{'#c0392b' if red else '#1b6ef3'}'>"
                        f"{vals[key]}</span>")

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
        if getattr(self, "dashboard", None) is not None:
            self.dashboard.refresh_header()

    def _tick(self):
        self.clock.setText(datetime.now().strftime("%A, %d %B %Y     %I:%M:%S %p"))
        if self.stack.currentWidget() is self.dashboard:
            self.dashboard.tick()

    def closeEvent(self, event):
        for dlg in list(getattr(self, "invoice_windows", [])):     # unsaved invoices ask before closing
            dlg.show()
            if not dlg.close():
                event.ignore()
                return
        if not self.skip_exit_backup and self.db.conn is not None:
            backup.auto_backup_on_exit(self.db)   # never blocks closing, even if it fails
        self.db.close()  # writes the final encrypted snapshot (no-op after a restore)
        super().closeEvent(event)
