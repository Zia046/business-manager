"""Small reusable UI helpers."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QGraphicsDropShadowEffect, QHeaderView, QTableWidget,
                               QTableWidgetItem)


def add_shadow(widget, blur=28, dy=6, alpha=60):
    """Soft warm shadow under a card (the glass look). Cheap: used only on a few big cards."""
    fx = QGraphicsDropShadowEffect(widget)
    fx.setBlurRadius(blur)
    fx.setOffset(0, dy)
    fx.setColor(QColor(190, 90, 70, alpha))
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
    t.setStyleSheet("QTableWidget { alternate-background-color: #fffaf7; gridline-color: #f6e6df; }"
                    "QHeaderView::section { background: #fdf1ec; padding: 8px; border: none; font-weight: 600; }")
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
