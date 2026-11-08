"""Dashboard: shop details, clock and calendar, sales graphs (daily / weekly / monthly / yearly),
profit & loss graph and the numbers that matter. Money totals and profit are shown to the owner only."""
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QCalendarWidget, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
                               QVBoxLayout, QWidget)

from ..reports import charts
from ..services import backup, masters, reports as R
from .theme import MUTED
from .widgets import make_table, money, set_row

CARD = "background: rgba(255,255,255,0.8); border: 1px solid rgba(255,255,255,0.95); border-radius: 16px; padding: 8px;"


def _pix(png: bytes) -> QPixmap:
    p = QPixmap()
    p.loadFromData(png, "PNG")
    return p


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
        outer.setContentsMargins(22, 14, 22, 14)
        outer.setSpacing(18)
        left, right = QVBoxLayout(), QVBoxLayout()
        left.setSpacing(12)
        outer.addLayout(left, 1)
        outer.addLayout(right)

        # ---- shop details (logo first) ----
        head = QHBoxLayout()
        self.logo = QLabel(alignment=Qt.AlignCenter)
        self.logo.setFixedSize(96, 96)
        head.addWidget(self.logo)
        info = QVBoxLayout()
        self.name = QLabel()
        self.name.setStyleSheet("font-size: 26px; font-weight: 800; letter-spacing: 2px;")
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

        # ---- number cards ----
        self.cards = {}
        grid = QGridLayout()
        grid.setSpacing(8)
        keys = [("today_sales", "Today's Sale"), ("today_invoices", "Today's Bills"), ("month_sales", "This Month Sale"),
                ("phones_in_stock", "Phones in Stock"), ("low_stock", "Low-stock Items"),
                ("qist_overdue", "Qist Overdue"), ("open_repairs", "Open Repairs")]
        if self.owner:
            keys += [("cash", "Cash in Hand"), ("receivable", "Customers Owe You"), ("month_profit", "Profit This Month"),
                     ("year_profit", "Profit This Year"), ("last_backup", "Last Backup")]
        for i, (key, title) in enumerate(keys):
            box = QLabel(alignment=Qt.AlignCenter)
            box.setStyleSheet(CARD)
            box.setMinimumWidth(120)
            grid.addWidget(box, i // 4, i % 4)
            self.cards[key] = (box, title)
        left.addLayout(grid)

        # ---- sales graphs ----
        self.sales_labels = {}
        sg = QGridLayout()
        sg.setSpacing(10)
        for i, kind in enumerate(("day", "week", "month", "year")):
            lab = QLabel()
            lab.setStyleSheet("background: rgba(255,255,255,0.8); border: 1px solid rgba(255,255,255,0.95); border-radius: 16px;")
            sg.addWidget(lab, i // 2, i % 2)
            self.sales_labels[kind] = lab
        left.addLayout(sg)
        self.profit_label = None
        if self.owner:
            self.profit_label = QLabel()
            self.profit_label.setStyleSheet("background: rgba(255,255,255,0.8); border: 1px solid rgba(255,255,255,0.95); border-radius: 16px;")
            left.addWidget(self.profit_label)

        # ---- lists ----
        lists = QHBoxLayout()
        self.top_t = self._list_box(lists, "Top selling this month", ["Product", "Qty", "Amount"])
        self.low_t = self._list_box(lists, "Low stock", ["Product", "In stock"])
        self.qist_t = self._list_box(lists, "Qist due soon / late", ["Customer", "Due", "Amount"])
        left.addLayout(lists)
        left.addStretch(1)

        # ---- clock and calendar ----
        self.clock_img = QLabel(alignment=Qt.AlignCenter)
        right.addWidget(self.clock_img)
        self.time_lbl = QLabel(alignment=Qt.AlignCenter)
        self.time_lbl.setStyleSheet("font-size: 28px; font-weight: 800;")
        self.date_lbl = QLabel(alignment=Qt.AlignCenter)
        self.date_lbl.setStyleSheet(f"color: {MUTED}; font-size: 14px; font-weight: 600;")
        right.addWidget(self.time_lbl)
        right.addWidget(self.date_lbl)
        self.calendar = QCalendarWidget()
        self.calendar.setGridVisible(True)
        self.calendar.setFixedWidth(300)
        self.calendar.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        right.addWidget(self.calendar)
        right.addStretch(1)
        self._today = None
        self.refresh_header()
        self.tick()

    @staticmethod
    def _list_box(parent_layout, title, headers):
        box = QVBoxLayout()
        lab = QLabel(f"<b>{title}</b>")
        box.addWidget(lab)
        t = make_table(headers, stretch_col=0)
        t.setFixedHeight(170)
        box.addWidget(t)
        parent_layout.addLayout(box, 1)
        return t

    # ---- shop details ----
    def refresh_header(self):
        co = masters.get_company(self.db)
        self.name.setText(co["name"].upper())
        self.details.setText("<br>".join(x for x in (co["address"], f"Mobile: {co['phone']}   Email: {co['email']}")
                                         if x))
        if co["logo_path"] and Path(co["logo_path"]).exists():
            self.logo.setPixmap(QPixmap(co["logo_path"]).scaled(90, 90, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.logo.clear()

    # ---- clock (called every second while visible) ----
    def tick(self):
        now = datetime.now()
        self.clock_img.setPixmap(_pix(charts.to_png(charts.clock_image(now.hour, now.minute, now.second, 170))))
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
        vals = {"today_sales": f"{d['today_sales']:,.0f}", "today_invoices": str(d["today_invoices"]),
                "month_sales": f"{x['month_sales']:,.0f}", "phones_in_stock": str(d["phones_in_stock"]),
                "low_stock": str(d["low_stock"]), "qist_overdue": str(d["qist_overdue"]),
                "open_repairs": str(x["open_repairs"]), "cash": f"{d['cash']:,.0f}",
                "receivable": f"{d['receivable']:,.0f}", "month_profit": f"{x['month_profit']:,.0f}",
                "year_profit": f"{x['year_profit']:,.0f}",
                "last_backup": ("Never!" if hours is None else "Just now" if hours < 1 else
                                f"{hours:.0f} hours ago" if hours < 48 else f"{hours / 24:.0f} days ago")}
        bad = {"low_stock": d["low_stock"] > 0, "qist_overdue": d["qist_overdue"] > 0,
               "month_profit": x["month_profit"] < 0, "year_profit": x["year_profit"] < 0,
               "last_backup": self.owner and (hours is None or hours > 48)}
        for key, (box, title) in self.cards.items():
            box.setText(f"<span style='color:#8a6f68;font-size:12px'>{title}</span><br>"
                        f"<span style='font-size:19px;font-weight:700;color:{'#c0392b' if bad.get(key) else '#e07a67'}'>"
                        f"{vals[key]}</span>")
        names = {"day": "Daily sales (last 14 days)", "week": "Weekly sales (last 8 weeks)",
                 "month": "Monthly sales (last 12 months)", "year": "Yearly sales"}
        for kind, lab in self.sales_labels.items():
            lab.setPixmap(_pix(charts.to_png(charts.bar_chart(R.sales_series(self.db, kind), names[kind],
                                                              size=(380, 240)))))
        if self.profit_label is not None:
            self.profit_label.setPixmap(_pix(charts.to_png(charts.bar_chart(
                R.profit_series(self.db), "Profit / Loss per month (green = profit, red = loss)", size=(770, 250),
                signed=True))))
        self._fill(self.top_t, [[r["name"], f"{r['qty']:g}", money(r["amount"])] for r in x["top_products"]], (1, 2))
        self._fill(self.low_t, [[r["name"], f"{r['qty']:g}"] for r in x["low_items"]], (1,))
        self._fill(self.qist_t, [[r["customer"], r["due_date"], money(r["remaining"])] for r in x["qist_due"]], (2,))

    @staticmethod
    def _fill(table, rows, numeric):
        table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            set_row(table, i, r, numeric)
