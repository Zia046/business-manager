"""Small drawing widgets for the home-page dashboard: bar chart (sales, profit and loss) and an analog clock.
They are drawn with QPainter only, so no extra library is needed."""
import math

from PySide6.QtCore import QPointF, QRectF, Qt, QTime
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from .theme import ACCENT, BORDER, MUTED, TEXT

GREEN, RED = QColor("#6ECDA0"), QColor("#D93C2D")


def short(v: float) -> str:
    """12,500 -> 12.5k ; 150,000 -> 1.5L (lakh) ; 25,000,000 -> 2.5Cr (crore)."""
    a, sign = abs(v), "-" if v < 0 else ""
    for limit, unit in ((1e7, "Cr"), (1e5, "L"), (1e3, "k")):
        if a >= limit:
            s = f"{a / limit:.1f}".rstrip("0").rstrip(".")
            return f"{sign}{s}{unit}"
    return f"{sign}{a:.0f}"


def nice_ceiling(v: float) -> float:
    """Round a positive number up to 1, 2, 2.5, 5 or 10 times a power of ten (for a tidy axis)."""
    if v <= 0:
        return 1.0
    exp = math.floor(math.log10(v))
    base = v / 10 ** exp
    for step in (1, 2, 2.5, 5, 10):
        if base <= step + 1e-9:
            return step * 10 ** exp
    return 10 ** (exp + 1)


class BarChart(QWidget):
    """Vertical bars. Positive values use `color`; negative values (a loss) are drawn red below the zero line."""

    def __init__(self, color=ACCENT, empty_text="No data yet", parent=None):
        super().__init__(parent)
        self.color = QColor(color)
        self.empty_text = empty_text
        self.labels, self.values = [], []
        self.setMinimumHeight(190)

    def set_data(self, labels, values):
        self.labels, self.values = list(labels), list(values)
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor("white"))
        left, right, top, bottom = 52, 10, 14, 30
        plot = QRectF(left, top, max(self.width() - left - right, 20), max(self.height() - top - bottom, 20))
        vals = self.values
        if not vals or all(abs(v) < 0.005 for v in vals):
            p.setPen(QColor(MUTED))
            p.drawText(self.rect(), Qt.AlignCenter, self.empty_text)
            return
        top_v = nice_ceiling(max([v for v in vals if v > 0], default=0))
        bot_v = -nice_ceiling(-min(v for v in vals if v < 0)) if any(v < 0 for v in vals) else 0.0
        if top_v == 1.0 and not any(v > 0 for v in vals):
            top_v = 0.0
        span = (top_v - bot_v) or 1.0

        def y(v):
            return plot.top() + plot.height() * (top_v - v) / span

        font = QFont(self.font())
        font.setPointSize(8)
        p.setFont(font)
        for i in range(5):                                   # grid lines with amounts on the left
            v = bot_v + span * i / 4
            yy = y(v)
            p.setPen(QPen(QColor("#f6e6df"), 1))
            p.drawLine(QPointF(plot.left(), yy), QPointF(plot.right(), yy))
            p.setPen(QColor(MUTED))
            p.drawText(QRectF(0, yy - 8, left - 6, 16), Qt.AlignRight | Qt.AlignVCenter, short(v))
        p.setPen(QPen(QColor(BORDER), 1.5))
        p.drawLine(QPointF(plot.left(), y(0)), QPointF(plot.right(), y(0)))

        n = len(vals)
        slot = plot.width() / n
        bar_w = min(slot * 0.62, 48)
        for i, v in enumerate(vals):
            x = plot.left() + slot * i + (slot - bar_w) / 2
            y0, y1 = y(0), y(v)
            if abs(v) >= 0.005:
                p.setPen(Qt.NoPen)
                p.setBrush(self.color if v >= 0 else RED)
                p.drawRoundedRect(QRectF(x, min(y0, y1), bar_w, max(abs(y1 - y0), 1.5)), 3, 3)
                if slot >= 36:                               # amount on top of (or below) the bar
                    p.setPen(QColor(TEXT))
                    ty = y1 - 15 if v >= 0 else y1 + 1
                    p.drawText(QRectF(x - 14, ty, bar_w + 28, 14), Qt.AlignCenter, short(v))
            if i < len(self.labels):
                p.setPen(QColor(MUTED))
                p.drawText(QRectF(plot.left() + slot * i, plot.bottom() + 6, slot, 16), Qt.AlignCenter,
                           self.labels[i])


class AnalogClock(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(150, 150)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor("white"))
        cx, cy = self.width() / 2, self.height() / 2
        r = min(self.width(), self.height()) / 2 - 6
        p.setBrush(QColor("#fffaf7"))
        p.setPen(QPen(QColor(ACCENT), 3))
        p.drawEllipse(QPointF(cx, cy), r, r)

        def at(angle_deg, radius):
            a = math.radians(angle_deg)
            return QPointF(cx + math.sin(a) * radius, cy - math.cos(a) * radius)

        for i in range(60):                                  # minute and hour ticks
            big = i % 5 == 0
            p.setPen(QPen(QColor(TEXT if big else MUTED), 2 if big else 1))
            p.drawLine(at(i * 6, r - (9 if big else 4)), at(i * 6, r - 2))
        f = QFont(self.font())
        f.setPointSize(9)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(TEXT))
        for num, ang in ((12, 0), (3, 90), (6, 180), (9, 270)):
            c = at(ang, r - 22)
            p.drawText(QRectF(c.x() - 10, c.y() - 9, 20, 18), Qt.AlignCenter, str(num))
        now = QTime.currentTime()
        hour = ((now.hour() % 12) + now.minute() / 60) * 30
        minute = (now.minute() + now.second() / 60) * 6
        for angle, length, width, color in ((hour, r * 0.5, 4, TEXT), (minute, r * 0.74, 3, TEXT),
                                            (now.second() * 6, r * 0.84, 1.5, "#d64541")):
            p.setPen(QPen(QColor(color), width, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(cx, cy), at(angle, length))
        p.setBrush(QColor(ACCENT))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(cx, cy), 4, 4)


def make_panel(title: str):
    """White rounded box with a bold title. Returns (frame, layout to add content to)."""
    frame = QFrame()
    frame.setObjectName("panel")
    frame.setStyleSheet("QFrame#panel { background: #FFFFFF; border: 1px solid #E8DDD2; border-radius: 14px; }"
                        "QFrame#panel QLabel { background: transparent; border: none; }")
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(14, 10, 14, 12)
    lay.setSpacing(6)
    if title:
        t = QLabel(title)
        t.setStyleSheet(f"font-size: 14px; font-weight: 700; color: {TEXT};")
        lay.addWidget(t)
    return frame, lay
