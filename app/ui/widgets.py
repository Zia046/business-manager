"""Small reusable UI helpers."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QGraphicsDropShadowEffect, QHeaderView, QPushButton, QTableWidget,
                               QTableWidgetItem)


def add_shadow(widget, blur=28, dy=6, alpha=60):
    """Very light shadow under a card. Cheap: used only on a few big cards."""
    fx = QGraphicsDropShadowEffect(widget)
    fx.setBlurRadius(blur)
    fx.setOffset(0, dy)
    fx.setColor(QColor(40, 30, 20, alpha))
    widget.setGraphicsEffect(fx)


def money(x) -> str:
    return f"{x:,.2f}"


def make_table(headers, stretch_col=1) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setSelectionMode(QAbstractItemView.SingleSelection)
    t.setAlternatingRowColors(True)
    t.verticalHeader().setVisible(False)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    t.horizontalHeader().setSectionResizeMode(stretch_col, QHeaderView.Stretch)
    return t


def set_row(table: QTableWidget, row: int, values, numeric_cols=(), highlight=None):
    for col, v in enumerate(values):
        item = QTableWidgetItem("" if v is None else str(v))
        if col in numeric_cols:
            item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        if highlight:
            item.setBackground(highlight)
        table.setItem(row, col, item)


def selected_id(table: QTableWidget):
    """ID is always kept in column 0."""
    rows = table.selectionModel().selectedRows()
    return int(table.item(rows[0].row(), 0).text()) if rows else None


def remove_button(slot, text="Remove", tooltip="") -> QPushButton:
    """The standard red Remove button (style 'remove' in theme.py). Used in table rows and under lists."""
    b = QPushButton(text)
    b.setObjectName("remove")
    b.setAutoDefault(False)
    if tooltip:
        b.setToolTip(tooltip)
    b.clicked.connect(slot)
    return b


def size_line_columns(table: QTableWidget, widths: dict, stretch_col: int, button_col=None):
    """Column widths for an entry table (Sale Invoice, Stock Purchase ...): every column is at least as wide as
    its heading needs, the button column fits a whole 'Remove', and the product column takes the spare room
    (it shrinks first when the window is small)."""
    head = table.horizontalHeader()
    head.setSectionResizeMode(QHeaderView.Interactive)
    head.setSectionResizeMode(stretch_col, QHeaderView.Stretch)
    head.setDefaultAlignment(Qt.AlignCenter | Qt.TextWordWrap)
    head.setMinimumSectionSize(36)
    probe = None
    if button_col is not None:
        probe = remove_button(lambda: None)
        probe.setParent(table.viewport())           # styled like the real buttons inside the rows
        probe.ensurePolished()
    for c, w in widths.items():
        need = head.sectionSizeHint(c) + 4          # heading text + padding
        if c == button_col and probe is not None:
            need = max(need, probe.sizeHint().width() + 10)   # + the button's own margins
        table.setColumnWidth(c, max(w, need))
    if probe is not None:
        probe.deleteLater()
