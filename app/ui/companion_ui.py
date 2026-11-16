"""Mobile App (Android): turn the Wi-Fi connection on, pair a phone with a 6-digit code, remove a phone.

Also the bridge that lets the server threads ask the main thread to read the database."""
import threading

from PySide6.QtCore import QObject, Qt, QTimer, Signal, Slot
from PySide6.QtWidgets import (QCheckBox, QDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout)

from ..services import companion
from ..services.companion_server import CompanionServer, local_addresses
from .theme import C_GREEN, C_RED, NAVY
from .widgets import make_table, set_row


class MainThreadRunner(QObject):
    """run(job) may be called from any thread; job() itself always runs on the main (GUI) thread, the only
    thread that may use the database. The caller waits for the answer (or the exception)."""
    _call = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._call.connect(self._execute, Qt.QueuedConnection)

    @Slot(object)
    def _execute(self, box):
        try:
            box["result"] = box["job"]()
        except BaseException as exc:            # handed back to the thread that asked
            box["error"] = exc
        box["done"].set()

    def run(self, job, timeout=15):
        if threading.current_thread() is threading.main_thread():
            return job()
        box = {"job": job, "done": threading.Event()}
        self._call.emit(box)
        if not box["done"].wait(timeout):
            raise TimeoutError()
        if "error" in box:
            raise box["error"]
        return box["result"]


class CompanionService:
    """Owned by the main window: the server, the pairing code and the on/off switch."""

    def __init__(self, window):
        self.window = window
        self.runner = MainThreadRunner(window)
        self.pairing = companion.Pairing()
        self.server = CompanionServer(self.runner.run, lambda: window.db, self.pairing)

    def start_if_enabled(self):
        if companion.is_enabled(self.window.db):
            self.server.start()

    def set_enabled(self, on) -> bool:
        companion.set_enabled(self.window.db, on)
        if on:
            return self.server.start()
        self.pairing.stop()
        self.server.stop()
        return True

    def stop(self):
        self.server.stop()


class CompanionDialog(QDialog):
    def __init__(self, service: CompanionService, parent=None):
        super().__init__(parent)
        self.service, self.db = service, service.window.db
        self.setWindowTitle("Mobile App (Android) - Burhan Nexus Business Companion")
        self.resize(640, 560)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        intro = QLabel("The Android app shows your Outstanding list on your phone and sends payment reminders. "
                       "It reads the data from this computer over your own Wi-Fi; nothing goes to the internet.")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        self.enable = QCheckBox("Allow the Android app to connect (same Wi-Fi only)")
        self.enable.setChecked(companion.is_enabled(self.db))
        self.enable.toggled.connect(self._toggle)
        lay.addWidget(self.enable)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)

        self.pair_btn = QPushButton("Pair a new phone")
        self.pair_btn.setAutoDefault(False)
        self.pair_btn.clicked.connect(self._pair)
        lay.addWidget(self.pair_btn)
        self.code = QLabel("")
        self.code.setAlignment(Qt.AlignCenter)
        self.code.setWordWrap(True)
        lay.addWidget(self.code)

        lay.addWidget(QLabel("<b>Paired phones</b>"))
        self.table = make_table(["Phone", "Paired on"], stretch_col=0)
        lay.addWidget(self.table, 1)
        row = QHBoxLayout()
        remove = QPushButton("Remove Selected Phone")
        remove.setObjectName("secondary")
        remove.setAutoDefault(False)
        remove.clicked.connect(self._remove)
        close = QPushButton("Close")
        close.setObjectName("secondary")
        close.setAutoDefault(False)
        close.clicked.connect(self.accept)
        row.addWidget(remove)
        row.addStretch()
        row.addWidget(close)
        lay.addLayout(row)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh)
        self.timer.start(1000)
        self._devices = []
        self._refresh()

    def _toggle(self, on):
        if not self.service.set_enabled(on) and on:
            QMessageBox.warning(self, "Mobile App", self.service.server.error or "Could not start the connection.")
        self._refresh()

    def _pair(self):
        if not self.service.server.running():
            QMessageBox.information(self, "Mobile App", "Turn the connection on first (tick the box above).")
            return
        self.service.pairing.start()
        self._refresh()

    def _remove(self):
        sel = self.table.selectionModel().selectedRows()
        if not sel:
            QMessageBox.information(self, "Mobile App", "Select a phone first.")
            return
        dev = self._devices[sel[0].row()]
        if QMessageBox.question(self, "Remove", f"Remove '{dev['name']}'? It will not be able to read your data "
                                "until it is paired again.") == QMessageBox.Yes:
            companion.remove_device(self.db, dev["id"])
            self._refresh()

    def _refresh(self):
        srv = self.service.server
        if srv.running():
            addrs = ", ".join(local_addresses()) or "no network found"
            text = (f"<span style='color:{C_GREEN}'><b>Connection is ON.</b></span> This computer on the network: "
                    f"{addrs} (port {srv.http_port}). The phone finds it by itself.")
            if srv.error:
                text += f"<br><span style='color:{C_RED}'>{srv.error}</span>"
        elif self.enable.isChecked():
            text = f"<span style='color:{C_RED}'><b>Could not start.</b> {srv.error}</span>"
        else:
            text = "Connection is OFF. The Android app cannot read anything."
        self.status.setText(text)
        p = self.service.pairing
        if p.active():
            self.code.setText(f"<div style='font-size:13px'>Type this code in the Android app:</div>"
                              f"<div style='font-size:44px; font-weight:800; color:{NAVY}; letter-spacing:6px'>"
                              f"{p.code[:3]} {p.code[3:]}</div>"
                              f"<div style='font-size:12px'>valid for {p.seconds_left()} seconds, for one phone</div>")
        else:
            self.code.setText("")
        devs = companion.devices(self.db)
        if [d["id"] for d in devs] != [d["id"] for d in self._devices]:
            self._devices = devs
            self.table.setRowCount(len(devs))
            for i, d in enumerate(devs):
                set_row(self.table, i, [d["name"], d["paired_at"][:16]])
