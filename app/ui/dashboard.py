"""Dashboard: clean statistic cards, sales & profit analytics, recent transactions, low-stock alerts and top sellers.
Money totals and profit are shown to the owner only (staff see the shop-floor numbers)."""
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QCalendarWidget, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
                               QVBoxLayout, QWidget)

from ..reports import charts, home_icons
from ..services import backup, masters, reports as R
from .theme import LINE, MUTED, SUCCESS_BG, SUCCESS_TEXT, SURFACE, TEXT, WARN_BG, WARN_TEXT
from .widgets import make_table, money, set_row

PANEL = f"background: {SURFACE}; border: 1px solid {LINE}; border-radius: 14px;"
PILL = {"mint": f"background: {SUCCESS_BG}; color: {SUCCESS_TEXT}; border-radius: 9px; padding: 2px 10px; font-size: 11px; font-weight: 700;",
        "yellow": f"background: {WARN_BG}; color: {WARN_TEXT}; border-radius: 9px; padding: 2px 10px; font-size: 11px; font-weight: 700;"}
# which small picture each card uses (pictures come from the shared icon set)
ICON = {"today_sales": "today_sales", "month_sales": "today_sales", "month_purchases": "low_stock",
        "month_profit": "cash", "month_expenses": "cash", "receivable": "receivable", "payable": "receivable",
        "stock": "low_stock", "low_stock": "low_stock", "cash": "cash", "phones_in_stock": "phones_in_stock",
        "qist_overdue": "qist_overdue", "last_backup": "last_backup"}


def _pix(png: bytes) -> QPixmap:
    p = QPixmap()
    p.loadFromData(png, "PNG")
    return p


class StatCard(QFrame):
    """One statistic: small icon, title, big value and an optional mint / yellow status pill."""

    def __init__(self, title, icon_key=None, compact=False):
        super().__init__()
        self.setObjectName("stat")
        self.setStyleSheet(f"QFrame#stat {{ {PANEL} }} QFrame#stat QLabel {{ background: transparent; border: none; }}")
        self.setMinimumHeight(86 if compact else 118)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(4)
        top = QHBoxLayout()
        top.setSpacing(8)
        if icon_key and not compact:
            ic = QLabel()
            ic.setPixmap(_pix(home_icons.badge_png(icon_key, 30)))
            ic.setFixedSize(30, 30)
            top.addWidget(ic)
        t = QLabel(title)
        t.setStyleSheet(f"color: {MUTED}; font-size: 13px; font-weight: 600;")
        top.addWidget(t, 1)
        lay.addLayout(top)
        self.value = QLabel("-")
        self.value.setStyleSheet(f"color: {TEXT}; font-size: {20 if compact else 27}px; font-weight: 800;")
        lay.addWidget(self.value)
        self.pill = QLabel()
        self.pill.hide()
        row = QHBoxLayout()
        row.addWidget(self.pill)
        row.addStretch(1)
        lay.addLayout(row)

    def set(self, value, pill=None, kind="yellow"):
        self.value.setText(value)
        if pill:
            self.pill.setText(pill)
            self.pill.setStyleSheet(PILL[kind])
            self.pill.show()
        else:
            self.pill.hide()


class DashboardPage(QScrollArea):
    home_requested = Signal()

    def __init__(self, db, user, parent=None):
        super().__init__(parent)
        self.db, self.user = db, user
        self.owner = user.get("role", "owner") == "owner"
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        body = QWidget(objectName="home")
        self.setWidget(body)
        outer = QHBoxLayout(body)
        outer.setContentsMargins(26, 20, 26, 18)
        outer.setSpacing(22)
        left, right = QVBoxLayout(), QVBoxLayout()
        left.setSpacing(16)
        outer.addLayout(left, 1)
        outer.addLayout(right)

        # ---- title row: logo, shop name, details ----
        head = QHBoxLayout()
        self.logo = QLabel(alignment=Qt.AlignCenter)
        self.logo.setFixedSize(60, 60)
        head.addWidget(self.logo)
        info = QVBoxLayout()
        info.setSpacing(2)
        self.name = QLabel()
        self.name.setStyleSheet("font-size: 24px; font-weight: 800;")
        self.name.setWordWrap(True)
        self.details = QLabel()
        self.details.setStyleSheet(f"color: {MUTED}; font-size: 13px;")
        self.details.setWordWrap(True)
        info.addWidget(self.name)
        info.addWidget(self.details)
        head.addLayout(info, 1)
        home = QPushButton("Home Screen")
        home.setObjectName("secondary")
        home.clicked.connect(self.home_requested.emit)
        head.addWidget(home, 0, Qt.AlignTop)
        left.addLayout(head)

        # ---- statistic cards ----
        self.cards = {}
        titles = {"today_sales": "Today's Revenue", "month_sales": "Total Sales (this month)",
                  "month_purchases": "Total Purchases (this month)", "month_profit": "Net Profit (this month)",
                  "month_expenses": "Total Expenses (this month)", "receivable": "Customer Receivables",
                  "payable": "Supplier Payables", "stock": "Available Stock", "low_stock": "Low-stock Items",
                  "cash": "Cash in Hand", "year_profit": "Profit This Year", "today_invoices": "Today's Bills",
                  "phones_in_stock": "Phones in Stock", "qist_overdue": "Qist Overdue",
                  "open_repairs": "Open Repairs", "last_backup": "Last Backup"}
        if self.owner:
            main = ["today_sales", "month_sales", "month_purchases", "month_profit", "month_expenses", "receivable",
                    "payable", "stock"]
            more = ["cash", "year_profit", "today_invoices", "phones_in_stock", "low_stock", "qist_overdue",
                    "open_repairs", "last_backup"]
        else:
            main = ["today_sales", "month_sales", "stock", "low_stock"]
            more = ["today_invoices", "phones_in_stock", "qist_overdue", "open_repairs"]
        for keys, compact in ((main, False), (more, True)):
            grid = QGridLayout()
            grid.setHorizontalSpacing(14)
            grid.setVerticalSpacing(14)
            for i, key in enumerate(keys):
                card = StatCard(titles[key], ICON.get(key), compact)
                grid.addWidget(card, i // 4, i % 4)
                self.cards[key] = card
            for c in range(4):
                grid.setColumnStretch(c, 1)
            left.addLayout(grid)

        # ---- sales & profit analytics ----
        left.addWidget(self._section("Sales & Profit Analytics"))
        self.sales_labels = {}
        sg = QGridLayout()
        sg.setSpacing(14)
        for i, kind in enumerate(("day", "week", "month", "year")):
            lab = QLabel(alignment=Qt.AlignCenter)
            lab.setStyleSheet(PANEL)
            sg.addWidget(lab, i // 2, i % 2)
            self.sales_labels[kind] = lab
        left.addLayout(sg)
        self.profit_label = None
        if self.owner:
            self.profit_label = QLabel(alignment=Qt.AlignCenter)
            self.profit_label.setStyleSheet(PANEL)
            left.addWidget(self.profit_label)

        # ---- lists ----
        lists = QGridLayout()
        lists.setHorizontalSpacing(14)
        lists.setVerticalSpacing(14)
        self.recent_t = self._list_box(lists, 0, 0, "Recent Transactions", ["Date", "Type", "No", "Party", "Amount"], 3)
        self.low_t = self._list_box(lists, 0, 1, "Low Stock Alerts", ["Product", "In stock"], 0)
        self.top_t = self._list_box(lists, 1, 0, "Top Selling Products (this month)", ["Product", "Qty", "Amount"], 0)
        self.qist_t = self._list_box(lists, 1, 1, "Qist due soon / late", ["Customer", "Due", "Amount"], 0)
        lists.setColumnStretch(0, 1)
        lists.setColumnStretch(1, 1)
        left.addLayout(lists)
        left.addStretch(1)

        # ---- clock and calendar ----
        side = QFrame()
        side.setObjectName("sidecard")
        side.setStyleSheet(f"QFrame#sidecard {{ {PANEL} }} QFrame#sidecard QLabel {{ background: transparent; border: none; }}")
        sl = QVBoxLayout(side)
        sl.setContentsMargins(14, 14, 14, 14)
        self.clock_img = QLabel(alignment=Qt.AlignCenter)
        sl.addWidget(self.clock_img)
        self.time_lbl = QLabel(alignment=Qt.AlignCenter)
        self.time_lbl.setStyleSheet("font-size: 26px; font-weight: 800;")
        self.date_lbl = QLabel(alignment=Qt.AlignCenter)
        self.date_lbl.setStyleSheet(f"color: {MUTED}; font-size: 13px; font-weight: 600;")
        sl.addWidget(self.time_lbl)
        sl.addWidget(self.date_lbl)
        self.calendar = QCalendarWidget()
        self.calendar.setGridVisible(False)
        self.calendar.setFixedWidth(280)
        self.calendar.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        sl.addWidget(self.calendar)
        right.addWidget(side)
        right.addStretch(1)
        self._today = None
        self.refresh_header()
        self.tick()

    @staticmethod
    def _section(text):
        lab = QLabel(text)
        lab.setStyleSheet("font-size: 17px; font-weight: 800; padding-top: 6px;")
        return lab

    @staticmethod
    def _list_box(grid, row, col, title, headers, stretch_col):
        frame = QFrame()
        frame.setObjectName("listbox")
        frame.setStyleSheet(f"QFrame#listbox {{ {PANEL} }} QFrame#listbox QLabel {{ background: transparent; border: none; }}")
        box = QVBoxLayout(frame)
        box.setContentsMargins(14, 12, 14, 12)
        box.setSpacing(8)
        lab = QLabel(title)
        lab.setStyleSheet("font-size: 14px; font-weight: 700;")
        box.addWidget(lab)
        t = make_table(headers, stretch_col=stretch_col)
        t.setFixedHeight(190)
        t.setStyleSheet("QTableWidget { border: none; background: transparent; }")
        box.addWidget(t)
        grid.addWidget(frame, row, col)
        return t

    # ---- shop details ----
    def refresh_header(self):
        co = masters.get_company(self.db)
        self.name.setText(co["name"].upper())
        self.details.setText("<br>".join(x for x in (co["address"], f"Mobile: {co['phone']}   Email: {co['email']}")
                                         if x))
        if co["logo_path"] and Path(co["logo_path"]).exists():
            self.logo.setPixmap(QPixmap(co["logo_path"]).scaled(56, 56, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.logo.clear()

    # ---- clock (called every second while visible) ----
    def tick(self):
        now = datetime.now()
        self.clock_img.setPixmap(_pix(charts.to_png(charts.clock_image(now.hour, now.minute, now.second, 160))))
        self.time_lbl.setText(now.strftime("%I:%M:%S %p"))
        self.date_lbl.setText(now.strftime("%A, %d %B %Y"))
        if self._today != now.date():                      # new day: move the calendar to today
            self._today = now.date()
            self.calendar.setSelectedDate(QDate.currentDate())

    # ---- data ----
    def refresh(self):
        try:
            self._refresh()
        except Exception:
            pass                                           # a dashboard problem must never stop the program

    def _refresh(self):
        d, x = R.dashboard(self.db), R.dashboard_extras(self.db)
        hours = backup.last_backup_info(self.db.data_dir)["age_hours"] if self.owner else None
        o = R.dashboard_overview(self.db) if self.owner else None
        stock = R.stock_position(self.db)
        units = sum(max(r["qty"], 0) for r in stock["rows"])
        backup_txt = ("Never!" if hours is None else "Just now" if hours < 1 else
                      f"{hours:.0f} hours ago" if hours < 48 else f"{hours / 24:.0f} days ago")
        stock_txt = f"{units:g} items" + (f"  |  {money(stock['total_value'])}" if self.owner else "")
        cards = {
            "today_sales": (f"{d['today_sales']:,.0f}", f"{d['today_invoices']} bills today" if d["today_invoices"] else None, "mint"),
            "month_sales": (f"{x['month_sales']:,.0f}", None, "mint"),
            "stock": (stock_txt, None, "mint"),
            "low_stock": (str(d["low_stock"]), "Reorder soon" if d["low_stock"] else None, "yellow"),
            "today_invoices": (str(d["today_invoices"]), None, "mint"),
            "phones_in_stock": (str(d["phones_in_stock"]), None, "mint"),
            "qist_overdue": (str(d["qist_overdue"]), "Overdue" if d["qist_overdue"] else None, "yellow"),
            "open_repairs": (str(x["open_repairs"]), None, "mint"),
        }
        if self.owner:
            cards.update({
                "month_purchases": (f"{o['month_purchases']:,.0f}", None, "mint"),
                "month_profit": (f"{o['month_profit']:,.0f}", "Profit" if o["month_profit"] >= 0 else "Loss",
                                 "mint" if o["month_profit"] >= 0 else "yellow"),
                "month_expenses": (f"{o['month_expenses']:,.0f}", None, "mint"),
                "receivable": (f"{o['receivable']:,.0f}", "Pending" if o["receivable"] > 0 else None, "yellow"),
                "payable": (f"{o['payable']:,.0f}", "To pay" if o["payable"] > 0 else None, "yellow"),
                "cash": (f"{d['cash']:,.0f}", None, "mint"),
                "year_profit": (f"{x['year_profit']:,.0f}", "Profit" if x["year_profit"] >= 0 else "Loss",
                                "mint" if x["year_profit"] >= 0 else "yellow"),
                "last_backup": (backup_txt, "Backup now" if hours is None or hours > 48 else None, "yellow"),
            })
        for key, card in self.cards.items():
            value, pill, kind = cards[key]
            card.set(value, pill, kind)
        names = {"day": "Daily sales (last 14 days)", "week": "Weekly sales (last 8 weeks)",
                 "month": "Monthly sales (last 12 months)", "year": "Yearly sales"}
        for kind, lab in self.sales_labels.items():
            lab.setPixmap(_pix(charts.to_png(charts.bar_chart(R.sales_series(self.db, kind), names[kind],
                                                              size=(380, 240)))))
        if self.profit_label is not None:
            self.profit_label.setPixmap(_pix(charts.to_png(charts.bar_chart(
                R.profit_series(self.db), "Profit / Loss per month (green = profit, red = loss)", size=(790, 250),
                signed=True))))
        recent = R.recent_transactions(self.db, 8, include_purchases=self.owner)
        self._fill(self.recent_t, [[r["date"][:10], r["kind"], r["no"], r["party"], money(r["amount"])]
                                   for r in recent], (4,))
        self._fill(self.top_t, [[r["name"], f"{r['qty']:g}", money(r["amount"])] for r in x["top_products"]], (1, 2))
        self._fill(self.low_t, [[r["name"], f"{r['qty']:g}"] for r in x["low_items"]], (1,))
        self._fill(self.qist_t, [[r["customer"], r["due_date"], money(r["remaining"])] for r in x["qist_due"]], (2,))

    @staticmethod
    def _fill(table, rows, numeric):
        table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            set_row(table, i, r, numeric)
