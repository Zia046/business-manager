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
if os.path.isdir(r"C:\Windows\Fonts"):                     # real Windows fonts in the screenshots
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

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
    # no input is cut off at the right edge, and no side scrolling is needed
    scroll = dialog.findChild(QtWidgets.QScrollArea)
    view = scroll.viewport()
    for w in scroll.widget().findChildren(QtWidgets.QWidget):
        if isinstance(w, (QtWidgets.QLineEdit, QtWidgets.QComboBox, QtWidgets.QAbstractSpinBox)) and w.isVisible() \
                and w.parent() is scroll.widget():
            right = w.mapTo(view, QPoint(w.width(), 0)).x()
            assert right <= view.width() + 1, (w.objectName() or type(w).__name__, right, view.width())
    assert not scroll.horizontalScrollBar().isVisible()
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


# ---------- Stock Purchase "Select from List", red Remove buttons, readable headings ----------
def _red(button):
    img = button.grab().toImage()
    c = img.pixelColor(8, img.height() // 2)
    return c.red() > 150 and c.green() < 110 and c.blue() < 120, (c.red(), c.green(), c.blue())


def _check_line_table(dlg, table, cols, button_col):
    head = table.horizontalHeader()
    for c in cols:
        if head.sectionResizeMode(c) == QtWidgets.QHeaderView.Stretch:
            continue
        assert table.columnWidth(c) >= head.sectionSizeHint(c), (table.horizontalHeaderItem(c).text(),
                                                                  table.columnWidth(c), head.sectionSizeHint(c))
    for r in range(table.rowCount()):
        btn = table.cellWidget(r, button_col)
        assert btn.objectName() == "remove" and btn.text() == "Remove"
        assert btn.width() >= btn.sizeHint().width(), (btn.width(), btn.sizeHint().width())   # whole word fits
        assert btn.height() >= btn.sizeHint().height() - 2
        ok, rgb = _red(btn)
        assert ok, rgb


def test_stock_purchase_select_from_list_and_headings(db, qapp, monkeypatch):
    import app.ui.stock_purchase as SP
    from app.ui.product_picker import ProductPickerDialog
    sup = masters.add_party(db, "supplier", "Ali Traders")
    cover = masters.add_product(db, "Back Cover A15", 500, purchase_price=200, category="Accessories",
                                barcode="80012345")
    masters.add_product(db, "Charger 25W", 900, purchase_price=600, category="Accessories")
    products_before = db.scalar("SELECT COUNT(*) FROM products")

    # the list window: search by barcode and by name
    pick = ProductPickerDialog(db, None, "", title="Stock Purchase - select product")
    assert pick.table.rowCount() == 2
    pick.search.setText("80012345")
    assert pick.table.rowCount() == 1 and pick.table.item(0, 1).text() == "Back Cover A15"
    pick.search.setText("charger")
    assert pick.table.rowCount() == 1 and pick.table.item(0, 1).text() == "Charger 25W"
    pick.close()

    class AutoPick(ProductPickerDialog):        # the user types the barcode and presses Enter
        def exec(self):
            self.search.setText("80012345")
            self._pick(0)
            return QtWidgets.QDialog.Accepted
    monkeypatch.setattr(SP, "ProductPickerDialog", AutoPick)

    dlg = SP.StockPurchaseDialog(db)
    dlg.show()
    qapp.processEvents()
    lst, newp = _button(dlg, "Select from List"), _button(dlg, "+ New Product")
    lay = [l for l in dlg.findChildren(QtWidgets.QHBoxLayout) if l.indexOf(lst) >= 0][0]
    assert lay.indexOf(lst) == lay.indexOf(newp) - 1 and lay.indexOf(dlg.search) < lay.indexOf(lst)
    _check_fits_window(dlg)
    lst.click()
    qapp.processEvents()
    assert [ln["product_id"] for ln in dlg.draft.lines] == [cover]
    assert dlg.draft.lines[0]["price"] == 200                          # saved purchase price filled as before
    assert db.scalar("SELECT COUNT(*) FROM products") == products_before   # nothing duplicated
    lst.click()                                                        # the same product again: same line, qty 2
    qapp.processEvents()
    assert len(dlg.draft.lines) == 1 and dlg.draft.lines[0]["qty"] == 2
    assert db.scalar("SELECT COUNT(*) FROM products") == products_before
    dlg.supplier.setCurrentIndex(dlg.supplier.findData(sup))
    qapp.processEvents()
    _check_line_table(dlg, dlg.table, range(len(SP.COLS)), SP.C_DEL)
    qty_col = SP.COLS.index("Quantity Purchase")
    assert dlg.table.columnWidth(qty_col) >= dlg.table.horizontalHeader().sectionSizeHint(qty_col)
    _shot(dlg, "stock_purchase_1366x768")
    dlg.resize(1000, 620)                                              # a smaller window
    qapp.processEvents()
    _check_line_table(dlg, dlg.table, range(len(SP.COLS)), SP.C_DEL)
    _shot(dlg, "stock_purchase_1000x620")
    dlg.table.cellWidget(0, SP.C_DEL).click()
    qapp.processEvents()
    assert dlg.table.rowCount() == 0 and dlg.draft.lines == []
    dlg.close()


def test_sale_invoice_remove_button_is_whole_and_red(db, qapp):
    from app.ui import sale_invoice as SI
    p1 = masters.add_product(db, "Glass Protector", 300, purchase_price=100, opening_stock=10, category="Accessories")
    p2 = masters.add_product(db, "Data Cable Type-C", 450, purchase_price=200, opening_stock=10, category="Accessories")
    dlg = SI.SaleInvoiceDialog(db)
    dlg.show()
    qapp.processEvents()
    for pid in (p1, p2):
        dlg._add_product(masters.search_products(db, str(pid))[0])
        qapp.processEvents()
    assert dlg.table.rowCount() == 2
    _check_line_table(dlg, dlg.table, range(len(SI.COLS)), SI.C_DEL)
    _shot(dlg, "sale_invoice_1366x768")
    dlg.resize(980, 640)
    qapp.processEvents()
    _check_line_table(dlg, dlg.table, range(len(SI.COLS)), SI.C_DEL)
    _shot(dlg, "sale_invoice_980x640")
    dlg.table.cellWidget(0, SI.C_DEL).click()
    qapp.processEvents()
    assert dlg.table.rowCount() == 1 and dlg.draft.lines[0]["product_id"] == p2
    dlg._force_close = True
    dlg.close()


def test_other_remove_buttons_share_the_red_style(db, qapp):
    from app.ui.labels_ui import LabelsDialog
    dlg = LabelsDialog(db)
    dlg.show()
    qapp.processEvents()
    b = _button(dlg, "Remove Selected")
    assert b.objectName() == "remove" and b.width() >= b.sizeHint().width()
    ok, rgb = _red(b)
    assert ok, rgb
    for other in ("Close",):
        assert _button(dlg, other).objectName() != "remove"
    dlg.close()


def _check_fits_window(dlg):
    area = dlg.screen().availableGeometry()
    assert dlg.width() <= area.width() and dlg.height() <= area.height()
