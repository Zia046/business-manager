"""Small reusable UI helpers."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget, QTableWidgetItem


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
    t.setStyleSheet("QTableWidget { alternate-background-color: #f7f9fc; gridline-color: #e5e9f0; }"
                    "QHeaderView::section { background: #eef2f7; padding: 8px; border: none; font-weight: 600; }")
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
