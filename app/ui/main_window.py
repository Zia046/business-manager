"""Home screen: banner with logo, company name and live date/time, 8 coloured buttons, today's numbers,
the fixed developer footer and the top menu bar."""
from datetime import datetime
from pathlib import Path

import time

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (QApplication, QFrame, QGridLayout, QHBoxLayout, QLabel, QMainWindow,
                               QPushButton, QScrollArea, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget)

from ..config import DEVELOPER_EMAIL, DEVELOPER_NAME, DEVELOPER_PHONE
from ..services import backup, masters, reports as R
from ..reports import home_icons
from ..services import permissions
from .dashboard import DashboardPage
from .layout_math import columns_for
from .menu_spec import HOME_BUTTONS, MENUS, SHORTCUTS
from .modules import open_module
from .responsive import FitWidthScrollArea, reflow
from .theme import BG, LINE, LINE_DARK, MUTED, NAVY, PRIMARY, PRIMARY_TINT, SURFACE, TEXT
from .widgets import add_shadow

IDLE_SECONDS = 90          # after this long without use, the Dashboard is shown

HOME_BG = BG

# (top, bottom, border, arrow colour): every home button looks the same - white card, thin border, blue arrow
CARD_COLORS = [(SURFACE, SURFACE, LINE_DARK, (37, 99, 235))] * 8

MENU_STYLE = f"""
QMenuBar {{ background: {NAVY}; color: white; padding: 3px 8px; }}
QMenuBar::item {{ background: transparent; color: white; padding: 8px 16px; border-radius: 6px; font-weight: 600; }}
QMenuBar::item:selected {{ background: {PRIMARY}; }}
QMenu {{ background: {SURFACE}; color: {TEXT}; border: 1px solid {LINE_DARK}; border-radius: 6px; padding: 4px; }}
QMenu::item {{ background: transparent; padding: 7px 30px 7px 16px; border-radius: 4px; }}
QMenu::item:selected {{ background: {PRIMARY_TINT}; color: {TEXT}; }}
QMenu::item:disabled {{ color: #A0AEC0; }}
"""


def _pm(png: bytes) -> QPixmap:
    p = QPixmap()
    p.loadFromData(png, "PNG")
    return p


CARD_HEIGHT = 100        # every home button has exactly this height
CARD_ICON = 64


class HomeCard(QPushButton):
    """One big coloured home button: picture on the left, number + name, round arrow on the right."""

    def __init__(self, index, label, key, parent=None):
        super().__init__(parent)
        top, bottom, border, arrow = CARD_COLORS[index % len(CARD_COLORS)]
        self.setObjectName(f"card{index}")
        self.setCursor(Qt.PointingHandCursor)
        # one size for every button: same height, and an Ignored width policy so the grid (not the text) sets
        # the width -> all columns come out exactly equal whatever the label length
        self.setFixedHeight(CARD_HEIGHT)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.setStyleSheet(
            f"QPushButton#card{index} {{ background: {SURFACE}; border: 1px solid {border}; border-radius: 14px; }}"
            f"QPushButton#card{index}:hover {{ background: #EFF6FF; border: 1px solid {PRIMARY}; }}"
            f"QPushButton#card{index}:pressed {{ background: {PRIMARY_TINT}; }}"
            f"QPushButton#card{index}:disabled {{ background: #E8EDF4; border: 1px solid {LINE}; }}")
        add_shadow(self, 14, 2, 22)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 8, 14, 8)
        lay.setSpacing(12)
        icon = QLabel(alignment=Qt.AlignCenter)
        icon.setPixmap(_pm(home_icons.home_icon_png(key, CARD_ICON)))
        icon.setFixedSize(CARD_ICON + 4, CARD_ICON + 4)
        text = QLabel(label, alignment=Qt.AlignVCenter | Qt.AlignLeft)
        text.setWordWrap(True)
        text.setMinimumWidth(0)
        text.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        text.setStyleSheet(f"color: {NAVY}; font-size: 16px; font-weight: 700;")
        go = QLabel(alignment=Qt.AlignCenter)
        go.setPixmap(_pm(home_icons.arrow_png(arrow, 32)))
        go.setFixedSize(34, 34)
        for w in (icon, text, go):
            w.setAttribute(Qt.WA_TransparentForMouseEvents)
            w.setStyleSheet(w.styleSheet() + " background: transparent;")
        lay.addWidget(icon)
        lay.addWidget(text, 1)
        lay.addWidget(go)


class ClickableFrame(QFrame):
    clicked = Signal()

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(ev)


class MainWindow(QMainWindow):
    def __init__(self, db, user=None):
        super().__init__()
        self.db = db
        self.user = user or {"login_id": "", "role": "owner", "name": ""}
        self.skip_exit_backup = False
        self.setStyleSheet(f"QMainWindow, QWidget#home {{ background: {BG}; }}" + MENU_STYLE)
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
        self.setMinimumSize(900, 560)
        self.setWindowState(Qt.WindowMaximized)       # fills the screen (never taller than it)

    # ---------- toolbar (menu bar) ----------
    def _build_menu(self):
        bar = self.menuBar()
        home = QAction("Home", self)
        home.triggered.connect(lambda _=False: self.show_home())
        bar.addAction(home)
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
        scroll = FitWidthScrollArea()                   # scrolls up/down only; never sideways
        scroll.setWidget(home)
        scroll.widthChanged.connect(self._relayout_home)
        self.stack.addWidget(scroll)
        self.home_page = scroll
        root = QVBoxLayout(home)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- banner: logo, company name, tagline, date and time ----
        banner = QFrame(objectName="banner")
        banner.setStyleSheet(f"QFrame#banner {{ background: {SURFACE}; border: none; border-bottom: 1px solid {LINE}; }}")
        bl = QHBoxLayout(banner)
        bl.setContentsMargins(40, 16, 30, 16)
        bl.setSpacing(26)
        self.logo = QLabel(alignment=Qt.AlignCenter)
        self.logo.setStyleSheet("background: transparent;")
        bl.addWidget(self.logo)
        mid = QVBoxLayout()
        mid.setSpacing(8)
        mid.addStretch()
        self.name = QLabel(alignment=Qt.AlignLeft | Qt.AlignVCenter)
        self.name.setStyleSheet(f"font-size: 40px; font-weight: 800; color: {NAVY}; background: transparent;")
        self.name.setWordWrap(True)
        mid.addWidget(self.name)
        ticks = QLabel("<span style='color:#2563EB'>&#10004;</span> Sales &nbsp;&nbsp;&nbsp; "
                       "<span style='color:#2563EB'>&#10004;</span> Purchase &nbsp;&nbsp;&nbsp; "
                       "<span style='color:#2563EB'>&#10004;</span> Accounts &nbsp;&nbsp;&nbsp; "
                       "<span style='color:#2563EB'>&#10004;</span> Reports")
        ticks.setStyleSheet(f"font-size: 16px; font-weight: 600; color: {NAVY}; background: transparent;")
        ticks.setWordWrap(True)
        mid.addWidget(ticks)
        mid.addStretch()
        bl.addLayout(mid, 1)
        clock_card = QFrame()
        clock_card.setStyleSheet(f"QFrame {{ background: {BG}; border: 1px solid {LINE}; border-radius: 12px; }}"
                                 " QLabel { border: none; background: transparent; }")
        add_shadow(clock_card, 12, 2, 18)
        cc = QVBoxLayout(clock_card)
        cc.setContentsMargins(18, 10, 18, 10)
        self.date_lbl = QLabel(alignment=Qt.AlignCenter)
        self.date_lbl.setStyleSheet(f"color: {NAVY}; font-size: 16px; font-weight: 700;")
        self.clock = QLabel(alignment=Qt.AlignCenter)
        self.clock.setStyleSheet(f"color: {NAVY}; font-size: 22px; font-weight: 800;")
        who = QLabel(f"{self.user.get('name') or self.user['login_id']}  ({self.user['role']})"
                     if self.user["login_id"] else "", alignment=Qt.AlignCenter)
        who.setStyleSheet(f"color: {MUTED}; font-size: 12px;")
        cc.addWidget(self.date_lbl)
        cc.addWidget(self.clock)
        cc.addWidget(who)
        bl.addWidget(clock_card, 0, Qt.AlignTop)
        root.addWidget(banner)

        # ---- the 8 coloured buttons (4 + 4) ----
        body = QVBoxLayout()
        body.setContentsMargins(32, 22, 32, 14)
        body.setSpacing(16)
        grid = QGridLayout()
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(18)
        self.home_grid = grid
        self.home_btns = []
        self.home_cols = None
        for i, (label, key) in enumerate(HOME_BUTTONS):
            btn = HomeCard(i, f"{i + 1}. {label}", key)
            btn.setEnabled(permissions.can_open(self.user["role"], key))
            btn.clicked.connect(lambda _=False, k=key, l=label: (open_module(self, k, l), self.refresh_dashboard()))
            self.home_btns.append(btn)
        reflow(grid, self.home_btns, 4)
        body.addLayout(grid)

        # ---- today at a glance ----
        strip = QFrame()
        add_shadow(strip, 14, 2, 20)
        strip.setStyleSheet(f"QFrame#strip {{ background: {SURFACE}; border: 1px solid {LINE}; border-radius: 14px; }}")
        strip.setObjectName("strip")
        sl = QGridLayout(strip)
        sl.setContentsMargins(14, 10, 14, 10)
        sl.setHorizontalSpacing(10)
        sl.setVerticalSpacing(8)
        self.strip_grid, self.strip_cells, self.strip_cols = sl, [], None
        self.cards = {}
        owner_only = {"cash", "receivable", "last_backup"}
        for key, title in (("today_sales", "Today's Sale"), ("cash", "Cash in Hand"),
                           ("receivable", "Customers Owe You"), ("low_stock", "Low-stock Items"),
                           ("phones_in_stock", "Phones in Stock"), ("qist_overdue", "Qist Overdue"),
                           ("last_backup", "Last Backup")):
            if key in owner_only and self.user["role"] != "owner":
                continue                      # staff do not see cash, money totals or backup state
            cell = ClickableFrame()
            cell.setObjectName("cell")
            cell.setMinimumWidth(0)
            cell.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            cell.setStyleSheet(f"QFrame#cell {{ background: {BG}; border: none; border-radius: 10px; }}"
                               " QLabel { background: transparent; }")
            cl = QHBoxLayout(cell)
            cl.setContentsMargins(8, 0, 8, 0)
            ic = QLabel()
            ic.setPixmap(_pm(home_icons.badge_png(key, 46)))
            ic.setFixedSize(46, 46)
            cl.addWidget(ic)
            col = QVBoxLayout()
            col.setSpacing(0)
            t = QLabel(title)
            t.setStyleSheet("color: #64748B; font-size: 13px; font-weight: 600;")
            v = QLabel("-")
            v.setStyleSheet("font-size: 22px; font-weight: 800; color: #1F2937;")
            col.addWidget(t)
            col.addWidget(v)
            cl.addLayout(col)
            if key == "cash" and self.user["role"] == "owner":
                cell.setCursor(Qt.PointingHandCursor)
                cell.setToolTip("Click to change Cash in Hand (password needed)")
                cell.clicked.connect(lambda: (open_module(self, "cash_in_hand", "Cash in Hand"),
                                              self.refresh_dashboard()))
            if key == "low_stock":
                cell.setCursor(Qt.PointingHandCursor)
                cell.setToolTip("Click to see the products that are low or finished")
                cell.clicked.connect(lambda: open_module(self, "low_stock", "Low Stock"))
            self.strip_cells.append(cell)
            self.cards[key] = (v, title)
        reflow(sl, self.strip_cells, len(self.strip_cells), max_cols=8)
        body.addWidget(strip)
        body.addStretch(1)
        root.addLayout(body, 1)

    def _relayout_home(self, width):
        """Buttons: 4 per row on a wide window, 2 on a medium one, 1 on a narrow one (never 3+1 or cut off)."""
        avail = width - 64
        cols = columns_for(avail, 250, spacing=20, max_cols=4, allowed=(4, 2, 1))
        cells = columns_for(avail, 190, spacing=10, max_cols=max(1, len(self.strip_cells)))
        if cols != self.home_cols:
            self.home_cols = cols
            reflow(self.home_grid, self.home_btns, cols)
        if cells != self.strip_cols:
            self.strip_cols = cells
            reflow(self.strip_grid, self.strip_cells, cells, max_cols=8)

    def _build_footer(self):
        """Fixed developer band: plain labels (no input), so it can be neither edited nor deleted."""
        band = QFrame(objectName="footer")
        band.setStyleSheet(f"QFrame#footer {{ background: {NAVY}; border: none; }} QLabel {{ background: transparent; }}")
        band.setFocusPolicy(Qt.NoFocus)
        lay = QHBoxLayout(band)
        lay.setContentsMargins(36, 10, 30, 10)
        self.slogan = QLabel("Grow Your Business with " + DEVELOPER_NAME)
        self.slogan.setStyleSheet("color: white; font-size: 20px; font-weight: 600;")
        lay.addWidget(self.slogan, 1)
        line = QFrame()
        line.setFrameShape(QFrame.VLine)
        line.setStyleSheet("color: rgba(255,255,255,0.6); background: rgba(255,255,255,0.6); max-width: 2px;")
        lay.addWidget(line)
        dev = QVBoxLayout()
        dev.setSpacing(2)
        d1 = QLabel(f"Developed by: <span style='color:#FDE68A;font-size:19px'><b>{DEVELOPER_NAME}</b></span>")
        d1.setStyleSheet("color: white; font-size: 15px; font-weight: 600;")
        d2 = QLabel(f"Mobile: <b>{DEVELOPER_PHONE}</b> &nbsp;&nbsp;&nbsp; Email: <b>{DEVELOPER_EMAIL}</b>")
        d2.setStyleSheet("color: white; font-size: 14px;")
        for w in (d1, d2):
            w.setTextInteractionFlags(Qt.NoTextInteraction)     # cannot be selected, edited or deleted
            w.setFocusPolicy(Qt.NoFocus)
            dev.addWidget(w)
        lay.addLayout(dev)
        end = QLabel("Together for Success")
        end.setStyleSheet("color: white; font-size: 14px; font-style: italic; padding-left: 24px;")
        lay.addWidget(end)
        self.slogan.setTextInteractionFlags(Qt.NoTextInteraction)
        return band

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
            box.setText(vals[key])
            box.setStyleSheet(f"font-size: 22px; font-weight: 800; color: {'#DC2626' if red else '#1F2937'};")

    def refresh_header(self):
        """Reload company name (CAPITAL LETTERS) and logo, e.g. after Company Information Edit."""
        co = masters.get_company(self.db)
        self.setWindowTitle(co["name"])
        self.name.setText(co["name"])
        self.slogan.setText("Grow Your Business with " + co["name"])
        if co["logo_path"] and Path(co["logo_path"]).exists():
            self.logo.setPixmap(QPixmap(co["logo_path"]).scaled(150, 150, Qt.KeepAspectRatio,
                                                                Qt.SmoothTransformation))
            self.logo.show()
        else:
            self.logo.clear()
            self.logo.hide()
        if getattr(self, "dashboard", None) is not None:
            self.dashboard.refresh_header()

    def _tick(self):
        now = datetime.now()
        self.date_lbl.setText(now.strftime("%A, %d %B %Y"))
        self.clock.setText(now.strftime("%I:%M:%S %p"))
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
