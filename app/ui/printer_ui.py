"""Utilities > Printer Settings: choose the thermal printer and the A4 printer."""
from PySide6.QtWidgets import (QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel, QMessageBox, QPushButton,
                               QVBoxLayout)

from ..config import APP_NAME
from ..services import backup
from .direct_print import list_printers
from .enter_safe import EnterSafeDialog

VIEWER = ("Ask every time (open the PDF, choose the printer there)", "")
DEFAULT = ("Windows default printer (print directly)", "__default__")


class PrinterSettingsDialog(EnterSafeDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Printer Settings")
        self.setMinimumWidth(560)
        s = backup.get_settings(db.data_dir)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        names = list_printers()
        form = QFormLayout()
        self.thermal = self._combo(names, s["thermal_printer"])
        self.a4 = self._combo(names, s["a4_printer"])
        self.width = QComboBox()
        self.width.addItem("80 mm roll (standard)", 80)
        self.width.addItem("58 mm roll (small)", 58)
        self.width.setCurrentIndex(1 if int(s["thermal_width"]) == 58 else 0)
        self.default_bill = QComboBox()
        self.default_bill.addItem("Thermal receipt", "thermal")
        self.default_bill.addItem("A4 invoice", "a4")
        self.default_bill.setCurrentIndex(1 if s["default_bill"] == "a4" else 0)
        form.addRow("Thermal printer (receipts)", self.thermal)
        form.addRow("Thermal paper width", self.width)
        form.addRow("A4 printer (invoices, vouchers)", self.a4)
        form.addRow("Sale invoice prints as", self.default_bill)
        lay.addLayout(form)
        info = QLabel("Choose a printer to print directly with no PDF window. Install the printer's driver in "
                      "Windows first (Settings > Printers & scanners), then press Refresh.")
        info.setObjectName("subtitle")
        info.setWordWrap(True)
        lay.addWidget(info)
        if not names:
            warn = QLabel("No printer is installed on this computer.")
            warn.setObjectName("error")
            lay.addWidget(warn)
        row = QHBoxLayout()
        refresh = QPushButton("Refresh Printers")
        refresh.setObjectName("secondary")
        refresh.clicked.connect(self._refresh)
        test = QPushButton("Test Print (thermal)")
        test.setObjectName("secondary")
        test.clicked.connect(self._test)
        save = QPushButton("Save")
        save.clicked.connect(self._save)
        close = QPushButton("Close")
        close.setObjectName("secondary")
        close.clicked.connect(self.reject)
        for b in (refresh, test):
            row.addWidget(b)
        row.addStretch()
        for b in (close, save):
            row.addWidget(b)
        lay.addLayout(row)

    @staticmethod
    def _combo(names, current):
        c = QComboBox()
        _fill(c, names, current)
        return c

    def _refresh(self):
        names = list_printers()
        for c in (self.thermal, self.a4):
            _fill(c, names, c.currentData())

    def _values(self):
        return dict(thermal_printer=self.thermal.currentData() or "", a4_printer=self.a4.currentData() or "",
                    thermal_width=self.width.currentData(), default_bill=self.default_bill.currentData())

    def _save(self):
        backup.save_settings(self.db.data_dir, **self._values())
        QMessageBox.information(self, APP_NAME, "Printer settings saved.")
        self.accept()

    def _test(self):
        backup.save_settings(self.db.data_dir, **self._values())      # test what is on the screen
        from ..reports.test_page import build_test_receipt
        from .direct_print import direct_print
        from .printing import deliver
        path = build_test_receipt(self.db.data_dir, int(self.width.currentData()))
        try:
            if self.thermal.currentData() and not self._viewer(self.thermal):
                direct_print(path, None if self.thermal.currentData() == "__default__" else self.thermal.currentData())
            else:
                deliver(self.db, path, thermal=True)
        except Exception as exc:
            QMessageBox.warning(self, "Test print", f"Could not print:\n{exc}")

    @staticmethod
    def _viewer(combo):
        return not combo.currentData()


def _fill(combo, names, current):
    combo.clear()
    combo.addItem(*VIEWER)
    combo.addItem(*DEFAULT)
    for n in names:
        combo.addItem(n, n)
    i = combo.findData(current)
    combo.setCurrentIndex(i if i >= 0 else 0)
