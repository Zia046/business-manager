"""Real Qt test of the two data-entry windows (runs where PySide6 is installed, e.g. the GitHub Windows build).

Checks that the window fits the screen, that Save / Cancel stay visible, that showing or hiding phone fields
does not resize or move the window, that Esc / Enter do not close it, and that saving still works.
Screenshots go to the folder in UI_SHOTS (if set)."""
import json
import os

import pytest

# a typical Windows 10 laptop screen (1366 x 768). The file name is given without a drive letter: Qt splits
# the platform setting at ':' so "C:\\..." would break it.
_cfg = "bm_offscreen_screen.json"           # in the folder the tests run from (same drive, short path)
with open(_cfg, "w") as f:
    json.dump({"screens": [{"name": "laptop", "x": 0, "y": 0, "width": 1366, "height": 768,
                            "logicalDpi": 96, "logicalBaseDpi": 96, "dpr": 1}]}, f)
try:
    _rel = os.path.relpath(_cfg).replace("\\", "/")
except ValueError:                      # temp folder on another drive
    _rel = None
os.environ.setdefault("QT_QPA_PLATFORM", f"offscreen:configfile={_rel}" if _rel and ":" not in _rel else "offscreen")
os.environ.setdefault("QT_FORCE_STDERR_LOGGING", "1")     # Qt messages into the log, also on Windows

QtWidgets = pytest.importorskip("PySide6.QtWidgets")
from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from app.services import auth, masters  # noqa: E402
from app.services.common import set_current_user  # noqa: E402

PW = "Strong#Pass123"


@pytest.fixture(scope="module")
def qapp():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from app.ui.theme import STYLESHEET
    app.setStyleSheet(STYLESHEET)
    return app


@pytest.fixture
def db(tmp_path, qapp):
    d = auth.register(tmp_path, "Burhan Nexus", "Sahara Center", "03475093446", "a@b.c", None, "admin", PW, PW)
    set_current_user({"login_id": "admin", "role": "owner", "name": "Owner"})
    yield d
    d.close()


def _shot(dialog, name):
    folder = os.environ.get("UI_SHOTS")
    if folder:
        os.makedirs(folder, exist_ok=True)
        dialog.grab().save(os.path.join(folder, name + ".png"))


def _button(dialog, text):
    for b in dialog.findChildren(QtWidgets.QPushButton):
        if b.text() == text:
            return b
    raise AssertionError(f"no button {text!r}")


def _fully_inside(dialog, widget):
    top_left = widget.mapTo(dialog, QPoint(0, 0))
    r = widget.rect().translated(top_left)
    return widget.isVisible() and dialog.rect().contains(r)


def _check_fits(dialog, *buttons):
    area = dialog.screen().availableGeometry()
    frame = dialog.frameGeometry()
    assert dialog.width() <= area.width() and dialog.height() <= area.height(), (dialog.size(), area)
    assert area.contains(dialog.geometry()), (dialog.geometry(), area)
    for text in buttons:
        assert _fully_inside(dialog, _button(dialog, text)), text
    return frame


def _phone_product(db):
    return masters.add_product(db, "Infinix Note 40 Pro", 29000, purchase_price=25000, category="Mobile Phone",
                               mobile_type="smartphone", ram_gb=8, storage_gb=256, brand="Infinix")


def test_edit_product_window_fits_and_keeps_its_buttons(db, qapp):
    from app.ui.products import ProductForm
    pid = _phone_product(db)
    p = db.one("SELECT * FROM products WHERE id=?", (pid,))
    dlg = ProductForm(db, p)
    dlg.show()
    qapp.processEvents()
    _shot(dlg, f"edit_product_{dlg.screen().availableGeometry().width()}x"
               f"{dlg.screen().availableGeometry().height()}")
    size, pos = dlg.size(), dlg.pos()
    _check_fits(dlg, "Save", "Cancel")
    # switching category and mobile type shows / hides rows: the window keeps its size and place
    acc = dlg.category.findText("Accessories")
    for idx in (acc, dlg.category.findText("Mobile Phone")):
        dlg.category.setCurrentIndex(idx)
        qapp.processEvents()
        assert (dlg.size(), dlg.pos()) == (size, pos)
        _check_fits(dlg, "Save", "Cancel")
    dlg.phone.type.setCurrentIndex(dlg.phone.type.findData("keypad"))
    qapp.processEvents()
    assert (dlg.size(), dlg.pos()) == (size, pos)
    dlg.phone.type.setCurrentIndex(dlg.phone.type.findData("smartphone"))
    # Esc and Enter do not close the window
    QTest.keyClick(dlg.name, Qt.Key_Escape)
    QTest.keyClick(dlg.name, Qt.Key_Return)
    qapp.processEvents()
    assert dlg.isVisible() and dlg.result() == 0
    # the scroll area really scrolls when the screen is short, the footer stays
    dlg.resize(dlg.width(), 380)
    qapp.processEvents()
    _check_fits(dlg, "Save", "Cancel")
    _shot(dlg, "edit_product_short_window")
    # saving works exactly as before
    dlg.resize(size)
    dlg.name.setText("Infinix Note 40 Pro (Edited)")
    dlg.purchase.setValue(24000)
    _button(dlg, "Save").click()
    qapp.processEvents()
    assert dlg.result() == QtWidgets.QDialog.Accepted
    q = db.one("SELECT name, avg_cost, ram_gb, storage_gb FROM products WHERE id=?", (pid,))
    assert q == {"name": "Infinix Note 40 Pro (Edited)", "avg_cost": 24000, "ram_gb": 8, "storage_gb": 256}


def test_new_product_window_fits(db, qapp):
    from app.ui.products import ProductForm
    dlg = ProductForm(db)
    dlg.show()
    qapp.processEvents()
    _check_fits(dlg, "Save", "Cancel")
    _shot(dlg, "new_product")
    dlg.close()


def test_second_hand_purchase_window_fits_and_saves(db, qapp):
    from app.services import used_phones
    from app.ui.used_phone_ui import UsedPhoneDialog
    dlg = UsedPhoneDialog(db)
    dlg.show()
    qapp.processEvents()
    _shot(dlg, f"purchase_2nd_hand_{dlg.screen().availableGeometry().width()}x"
               f"{dlg.screen().availableGeometry().height()}")
    size, pos = dlg.size(), dlg.pos()
    _check_fits(dlg, "Save Purchase", "Close", "Purchase History")
    for kind in ("keypad", "smartphone"):
        dlg.spec.type.setCurrentIndex(dlg.spec.type.findData(kind))
        qapp.processEvents()
        assert (dlg.size(), dlg.pos()) == (size, pos)
        _check_fits(dlg, "Save Purchase", "Close")
    QTest.keyClick(dlg.seller, Qt.Key_Escape)
    qapp.processEvents()
    assert dlg.isVisible()
    dlg.resize(dlg.width(), 380)
    qapp.processEvents()
    _check_fits(dlg, "Save Purchase", "Close")
    _shot(dlg, "purchase_2nd_hand_short_window")
    dlg.resize(size)
    # fill in and save: the same purchase as before the new layout
    dlg.seller.setText("Kamran")
    dlg.cnic.setText("1510112345671")
    dlg.model.setText("Infinix Hot 40")
    dlg.spec.ram.setValue(8)
    dlg.spec.storage.setValue(128)
    dlg.imei1.setText("861234500000011")
    dlg.price.setValue(20000)
    dlg.sale_price.setValue(26000)
    QtWidgets.QMessageBox.information = staticmethod(lambda *a, **k: None)   # no blocking pop-up in the test
    _button(dlg, "Save Purchase").click()
    qapp.processEvents()
    assert dlg.error.text() == ""
    h = used_phones.history(db)
    assert len(h) == 1 and (h[0]["seller_name"], h[0]["price"], h[0]["sale_price"], h[0]["ram_gb"]) == (
        "Kamran", 20000, 26000, 8)
    assert dlg.isVisible() and dlg.seller.text() == ""          # stays open for the next phone, as before
    dlg.close()
