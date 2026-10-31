"""Searchable customer/supplier drop-down shared by several windows."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QCompleter

from ..services import masters


def make_party_combo(db, kind, select_id=None, include_walkin=False, combo=None) -> QComboBox:
    combo = combo or QComboBox()
    combo.setEditable(True)
    combo.setInsertPolicy(QComboBox.NoInsert)
    combo.setMinimumWidth(320)
    rows = [r for r in masters.search_parties(db, kind, "") if include_walkin or not r["is_walkin"]]
    rows.sort(key=lambda r: r["name"].lower())
    combo.blockSignals(True)
    combo.clear()
    for r in rows:
        combo.addItem(f"{r['name']}  (ID {r['id']})", r["id"])
    comp = QCompleter([combo.itemText(i) for i in range(combo.count())], combo)
    comp.setCaseSensitivity(Qt.CaseInsensitive)
    comp.setFilterMode(Qt.MatchContains)
    combo.setCompleter(comp)
    idx = combo.findData(select_id) if select_id else -1
    combo.setCurrentIndex(idx if idx >= 0 else -1)
    combo.blockSignals(False)
    return combo


def combo_party_id(combo):
    """Selected party id, also when the user typed the full label by hand."""
    pid = combo.currentData()
    if pid is None:
        i = combo.findText(combo.currentText(), Qt.MatchFixedString)
        pid = combo.itemData(i) if i >= 0 else None
    return pid
