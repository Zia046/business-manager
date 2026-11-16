"""Mobile Type / RAM / Storage inputs used on every form where a phone is entered.

RAM and Storage are numbers only (the program adds 'GB'). For a keypad phone both rows are hidden."""
from PySide6.QtWidgets import QComboBox, QSpinBox

from ..services import phones


class PhoneFields:
    def __init__(self, form, mobile_type=None, ram_gb=None, storage_gb=None, allow_unknown=False):
        """Adds three rows to `form` (a QFormLayout). allow_unknown: an old record may stay 'Not specified'."""
        self.form = form
        self.type = QComboBox()
        if allow_unknown:
            self.type.addItem("Not specified (old record)", None)
        for key, label in phones.TYPES.items():
            self.type.addItem(label, key)
        idx = self.type.findData(mobile_type)
        self.type.setCurrentIndex(idx if idx >= 0 else 0)
        self.ram, self.storage = self._gb(ram_gb, 64), self._gb(storage_gb, 4096)
        form.addRow("Mobile Type *", self.type)
        form.addRow("RAM (GB) *", self.ram)
        form.addRow("Storage (GB) *", self.storage)
        self.type.currentIndexChanged.connect(self._sync)
        self.shown = True
        self._sync()

    @staticmethod
    def _gb(value, maximum):
        box = QSpinBox()
        box.setRange(0, maximum)
        box.setSuffix(" GB")
        box.setSpecialValueText("-")            # 0 = not entered
        box.setValue(int(value or 0))
        box.setToolTip("Type the number only, e.g. 8. GB is added by the program.")
        return box

    def _sync(self, *_):
        smart = self.shown and self.type.currentData() != "keypad"
        self.form.setRowVisible(self.type, self.shown)
        self.form.setRowVisible(self.ram, smart)
        self.form.setRowVisible(self.storage, smart)

    def set_shown(self, on: bool):
        """Hide all three rows when the product is not a mobile phone."""
        self.shown = bool(on)
        self._sync()

    def values(self) -> dict:
        t = self.type.currentData()
        keypad = t == "keypad"
        return {"mobile_type": t, "ram_gb": None if keypad else self.ram.value() or None,
                "storage_gb": None if keypad else self.storage.value() or None}
