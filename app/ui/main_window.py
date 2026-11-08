"""Home screen: banner with logo, company name and live date/time, 8 coloured buttons, today's numbers,
the fixed developer footer and the top menu bar."""
from datetime import datetime
from pathlib import Path

import time

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (QApplication, QFrame, QGridLayout, QHBoxLayout, QLabel, QMainWindow, QMenu,
                               QPushButton, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget)

from ..config import DEVELOPER_EMAIL, DEVELOPER_NAME, DEVELOPER_PHONE
from ..services import backup, masters, reports as R
from ..reports import home_icons
from ..services import permissions
from .dashboard import DashboardPage
from .menu_spec import HOME_BUTTONS, MENUS, SHORTCUTS
from .modules import open_module
from .theme import (BG, BG_DARK, CARD, CHARCOAL, CORAL, CORAL_DARK, CORAL_TINT, IVORY, LINE, LINE_DARK, MINT, MUTED,
                    YELLOW)
from .widgets import add_shadow

IDLE_SECONDS = 90          # after this long without use, the Dashboard is shown

NAVY = CHARCOAL
HOME_BG = IVORY

# (gradient top, gradient bottom, border, arrow colour) for each of the 8 home buttons, in order
# (top, bottom, border, arrow colour): every home button looks the same - white card, thin border, coral arrow
CARD_COLORS = [(CARD, CARD, LINE_DARK, (252, 100, 84))] * 8

MENU_STYLE = f"""
QMenu {{ background: {CARD}; color: {CHARCOAL}; border: 1px solid {LINE_DARK}; border-radius: 10px; padding: 6px; }}
QMenu::item {{ background: transparent; padding: 8px 30px 8px 16px; border-radius: 7px; }}
QMenu::item:selected {{ background: {CORAL_TINT}; color: {CHARCOAL}; }}
QMenu::item:disabled {{ color: #B3A89F; }}
"""

SIDEBAR_STYLE = f"""
QFrame#sidebar {{ background: {CHARCOAL}; border: none; }}
QFrame#sidebar QLabel {{ background: transparent; color: #ffffff; }}
QFrame#sidebar QPushButton {{ background: transparent; color: #E9E4DF; text-align: left; border: none;
    border-left: 4px solid transparent; border-radius: 0; padding: 11px 18px; font-size: 14px; font-weight: 600; }}
QFrame#sidebar QPushButton:hover {{ background: #3A3A3A; color: #ffffff; }}
QFrame#sidebar QPushButton[active="true"] {{ background: #343434; color: #ffffff; border-left: 4px solid {CORAL}; }}
QFrame#sidebar QPushButton::menu-indicator {{ image: none; width: 0; }}
"""


def _pm(png: bytes) -> QPixmap:
    p = QPixmap()
    p.loadFromData(png, "PNG")
    return p


class HomeCard(QPushButton):
    """One big coloured home button: picture on the left, number + name, round arrow on the right."""

    def __init__(self, index, label, key, parent=None):
        super().__init__(parent)
        top, bottom, border, arrow = CARD_COLORS[index % len(CARD_COLORS)]
        self.setObjectName(f"card{index}")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(118)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet(
            f"QPushButton#card{index} {{ background: {CARD}; border: 1px solid {border}; border-radius: 14px; }}"
            f"QPushButton#card{index}:hover {{ background: #FFF6F4; border: 1px solid {CORAL}; }}"
            f"QPushButton#card{index}:pressed {{ background: {CORAL_TINT}; }}"
            f"QPushButton#card{index}:disabled {{ background: #EFE8E1; border: 1px solid {LINE}; }}")
        add_shadow(self, 14, 2, 22)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(18, 8, 14, 8)
        lay.setSpacing(12)
        icon = QLabel(alignment=Qt.AlignCenter)
        icon.setPixmap(_pm(home_icons.home_icon_png(key, 88)))
        icon.setFixedSize(92, 92)
        text = QLabel(label, alignment=Qt.AlignVCenter | Qt.AlignLeft)
        text.setWordWrap(True)
        text.setStyleSheet(f"color: {NAVY}; font-size: 17px; font-weight: 700;")
        go = QLabel(alignment=Qt.AlignCenter)
        go.setPixmap(_pm(home_icons.arrow_png(arrow, 36)))
        go.setFixedSize(38, 38)
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
        self.setStyleSheet(f"QMainWindow, QWidget#home {{ background: {IVORY}; }}" + MENU_STYLE)
        self.menuBar().setVisible(False)          # navigation lives in the dark sidebar on the left
        QShortcut(QKeySequence("F2"), self, activated=lambda: open_module(self, "sale_invoice", "Sale Invoice"))
        QShortcut(QKeySequence("F5"), self, activated=self.show_dashboard)
        # pages: Home (7 buttons) and Dashboard; the developer line below them is always visible
        self.stack = QStackedWidget()
        container = QWidget(objectName="home")
        outer = QHBoxLayout(container)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_sidebar())
        right = QWidget(objectName="home")
        cl = QVBoxLayout(right)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        cl.addWidget(self.stack, 1)
        cl.addWidget(self._build_footer())
        outer.addWidget(right, 1)
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

    # ---------- sidebar (same menu items, names and shortcuts as before) ----------
    def _build_sidebar(self):
        bar = QFrame(objectName="sidebar")
        bar.setFixedWidth(232)
        bar.setStyleSheet(SIDEBAR_STYLE)
        lay = QVBoxLayout(bar)
        lay.setContentsMargins(0, 18, 0, 12)
        lay.setSpacing(2)
        self.side_logo = QLabel(alignment=Qt.AlignCenter)
        self.side_logo.setFixedHeight(84)
        lay.addWidget(self.side_logo)
        self.side_name = QLabel("", alignment=Qt.AlignCenter)
        self.side_name.setWordWrap(True)
        self.side_name.setStyleSheet("font-size: 17px; font-weight: 700; padding: 2px 12px 14px 12px;")
        lay.addWidget(self.side_name)
        self.nav = {}

        def nav_button(text, handler, key):
            b = QPushButton(text)
            b.setCursor(Qt.PointingHandCursor)
            b.setFocusPolicy(Qt.NoFocus)
            b.setProperty("active", False)
            if handler:
                b.clicked.connect(lambda _=False: handler())
            lay.addWidget(b)
            self.nav[key] = b
            return b

        nav_button("Dashboard", self.show_dashboard, "dashboard")
        nav_button("Home", self.show_home, "home")
        self.menus = []
        for title, items in MENUS:
            btn = nav_button(title + "   \u25B8", None, title)
            menu = QMenu(btn)
            for label, key in items:
                act = QAction(label, self)
                act.triggered.connect(lambda _=False, k=key, l=label: open_module(self, k, l))
                if not permissions.can_open(self.user["role"], key):
                    act.setEnabled(False)                      # staff: owner-only items are greyed out
                if key in SHORTCUTS and title in ("Sale/Purchase", "Payments/Receipts"):
                    act.setShortcut(QKeySequence(SHORTCUTS[key]))
                    self.addAction(act)                        # shortcuts keep working from every screen
                menu.addAction(act)
            btn.clicked.connect(lambda _=False, b=btn, m=menu: m.popup(b.mapToGlobal(b.rect().topRight())))
            self.menus.append(menu)
        lay.addStretch(1)
        who = QLabel(f"{self.user.get('name') or self.user['login_id']}  ({self.user['role']})"
                     if self.user["login_id"] else "")
        who.setStyleSheet("color: #BDB5AE; font-size: 12px; padding: 6px 18px;")
        lay.addWidget(who)
        self._mark_nav("home")
        return bar

    def _mark_nav(self, key):
        for k, b in self.nav.items():
            b.setProperty("active", k == key)
            b.style().unpolish(b)
            b.style().polish(b)

    # ---------- home page ----------
    def _build_home(self):
        home = QWidget(objectName="home")
        self.stack.addWidget(home)
        self.home_page = home
        root = QVBoxLayout(home)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- banner: logo, company name, tagline, date and time ----
        banner = QFrame(objectName="banner")
        banner.setStyleSheet(f"QFrame#banner {{ background: {CARD}; border: none; border-bottom: 1px solid {LINE}; }}")
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
        ticks = QLabel("<span style='color:#FC6454'>&#10004;</span> Sales &nbsp;&nbsp;&nbsp; "
                       "<span style='color:#FC6454'>&#10004;</span> Purchase &nbsp;&nbsp;&nbsp; "
                       "<span style='color:#FC6454'>&#10004;</span> Accounts &nbsp;&nbsp;&nbsp; "
                       "<span style='color:#FC6454'>&#10004;</span> Reports")
        ticks.setStyleSheet(f"font-size: 16px; font-weight: 600; color: {NAVY}; background: transparent;")
        mid.addWidget(ticks)
        mid.addStretch()
        bl.addLayout(mid, 1)
        clock_card = QFrame()
        clock_card.setStyleSheet(f"QFrame {{ background: {IVORY}; border: 1px solid {LINE}; border-radius: 12px; }}"
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
        for i, (label, key) in enumerate(HOME_BUTTONS):
            btn = HomeCard(i, f"{i + 1}. {label}", key)
            btn.setEnabled(permissions.can_open(self.user["role"], key))
            btn.clicked.connect(lambda _=False, k=key, l=label: (open_module(self, k, l), self.refresh_dashboard()))
            grid.addWidget(btn, i // 4, i % 4)
        for c in range(4):
            grid.setColumnStretch(c, 1)
        body.addLayout(grid, 1)

        # ---- today at a glance ----
        strip = QFrame()
        add_shadow(strip, 14, 2, 20)
        strip.setStyleSheet(f"QFrame#strip {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 14px; }}")
        strip.setObjectName("strip")
        sl = QHBoxLayout(strip)
        sl.setContentsMargins(14, 10, 14, 10)
        self.cards = {}
        owner_only = {"cash", "receivable", "last_backup"}
        first = True
        for key, title in (("today_sales", "Today's Sale"), ("cash", "Cash in Hand"),
                           ("receivable", "Customers Owe You"), ("low_stock", "Low-stock Items"),
                           ("phones_in_stock", "Phones in Stock"), ("qist_overdue", "Qist Overdue"),
                           ("last_backup", "Last Backup")):
            if key in owner_only and self.user["role"] != "owner":
                continue                      # staff do not see cash, money totals or backup state
            if not first:
                line = QFrame()
                line.setFrameShape(QFrame.VLine)
                line.setStyleSheet("color: #E8DDD2; background: #E8DDD2; max-width: 1px; border: none;")
                sl.addWidget(line)
            first = False
            cell = ClickableFrame()
            cell.setStyleSheet("QFrame { background: transparent; border: none; }")
            cl = QHBoxLayout(cell)
            cl.setContentsMargins(8, 0, 8, 0)
            ic = QLabel()
            ic.setPixmap(_pm(home_icons.badge_png(key, 46)))
            ic.setFixedSize(46, 46)
            cl.addWidget(ic)
            col = QVBoxLayout()
            col.setSpacing(0)
            t = QLabel(title)
            t.setStyleSheet("color: #7B7068; font-size: 13px; font-weight: 600;")
            v = QLabel("-")
            v.setStyleSheet("font-size: 22px; font-weight: 800; color: #282828;")
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
            sl.addWidget(cell, 1)
            self.cards[key] = (v, title)
        body.addWidget(strip)
        root.addLayout(body, 1)

    def _build_footer(self):
        """Fixed developer band: plain labels (no input), so it can be neither edited nor deleted."""
        band = QFrame(objectName="footer")
        band.setStyleSheet(f"QFrame#footer {{ background: {CHARCOAL}; border: none; }} QLabel {{ background: transparent; }}")
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
        d1 = QLabel(f"Developed by: <span style='color:#F3E16B;font-size:19px'><b>{DEVELOPER_NAME}</b></span>")
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
        self._mark_nav("dashboard")

    def show_home(self):
        self.stack.setCurrentWidget(self.home_page)
        self._mark_nav("home")

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
            box.setStyleSheet(f"font-size: 22px; font-weight: 800; color: {'#D92D20' if red else '#282828'};")

    def refresh_header(self):
        """Reload company name (CAPITAL LETTERS) and logo, e.g. after Company Information Edit."""
        co = masters.get_company(self.db)
        self.setWindowTitle(co["name"])
        self.name.setText(co["name"])
        self.side_name.setText(co["name"])
        if co["logo_path"] and Path(co["logo_path"]).exists():
            self.side_logo.setPixmap(QPixmap(co["logo_path"]).scaled(150, 76, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.side_logo.clear()
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
