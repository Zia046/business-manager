import os

import pytest

from app.db.connection import Database, WrongPasswordError
from app.services import auth, masters, payments, reports, trading
from app.services.common import BusinessError, customer_balance, stock_qty, supplier_balance

PW = "secret123"


@pytest.fixture
def env(tmp_path):
    db = auth.register(tmp_path, "Burhan Nexus", "Main Road", "03001234567", "a@b.com",
                       None, "admin", PW, PW)
    yield tmp_path, db
    db.close()


@pytest.fixture
def shop(env):
    _, db = env
    sup = masters.add_party(db, "supplier", "Phone Supplier")
    cust = masters.add_party(db, "customer", "Ali")
    prod = masters.add_product(db, "Samsung A15", sale_price=50000, purchase_price=0, tags="#mobile")
    return db, sup, cust, prod


# ---------- auth / encryption ----------
def test_data_file_is_encrypted_and_login_works(env):
    path, db = env
    db.close()
    raw = (path / "business.bmdb").read_bytes()
    assert b"SQLite format 3" not in raw and b"Burhan" not in raw
    assert auth.is_registered(path)
    db2 = auth.login(path, "admin", PW)
    assert masters.get_company(db2)["name"] == "Burhan Nexus"
    db2.close()


def test_wrong_credentials_and_lockout(env):
    path, db = env
    db.close()
    for _ in range(4):
        with pytest.raises(BusinessError, match="Invalid Login ID or Password"):
            auth.login(path, "admin", "wrong")
    with pytest.raises(BusinessError, match="Invalid Login ID or Password"):
        auth.login(path, "wrongid", PW)  # 5th failure triggers lock
    with pytest.raises(BusinessError, match="Too many"):
        auth.login(path, "admin", PW)


def test_registration_validation(tmp_path):
    with pytest.raises(BusinessError):
        auth.register(tmp_path, "X", "A", "123", "bad-email", None, "u", "secret123", "secret123")
    with pytest.raises(BusinessError, match="do not match"):
        auth.register(tmp_path, "X", "A", "03001234567", "a@b.com", None, "u", "secret123", "other12")


def test_change_password_rekeys(env):
    path, db = env
    auth.change_credentials(db, PW, "boss", "newpass99")
    db.close()
    with pytest.raises(BusinessError):
        auth.login(path, "admin", PW)
    auth.login(path, "boss", "newpass99").close()


# ---------- purchase / stock / weighted average ----------
def test_purchase_updates_stock_cost_supplier_cash(shop):
    db, sup, cust, prod = shop
    trading.create_purchase(db, sup, [{"product_id": prod, "qty": 10, "price": 40000}], paid=100000)
    assert stock_qty(db.conn, prod) == 10
    assert supplier_balance(db.conn, sup) == 300000
    assert reports.cash_in_hand(db) == -100000
    trading.create_purchase(db, sup, [{"product_id": prod, "qty": 10, "price": 42000}])
    p = db.one("SELECT * FROM products WHERE id=?", (prod,))
    assert p["avg_cost"] == 41000 and p["last_purchase_price"] == 42000


def test_purchase_requires_typed_price(shop):
    db, sup, _, prod = shop
    with pytest.raises(BusinessError):
        trading.create_purchase(db, sup, [{"product_id": prod, "qty": 1, "price": None}])


# ---------- sale / ledger / profit ----------
def _stocked(shop):
    db, sup, cust, prod = shop
    trading.create_purchase(db, sup, [{"product_id": prod, "qty": 10, "price": 40000}])
    return db, sup, cust, prod


def test_credit_sale_ledger_stock_profit(shop):
    db, sup, cust, prod = _stocked(shop)
    inv = trading.create_invoice(db, cust, [{"product_id": prod, "qty": 2, "price": 50000}],
                                 discount=1000, paid=40000)
    assert stock_qty(db.conn, prod) == 8
    assert customer_balance(db.conn, cust) == 99000 - 40000
    assert trading.invoice_profit(db, inv) == 99000 - 80000
    assert reports.cash_in_hand(db) == 40000
    pl = reports.profit_loss(db, "2000-01-01", "2999-12-31")
    assert pl["net_profit"] == 19000


def test_oversell_rolls_back_everything(shop):
    db, sup, cust, prod = _stocked(shop)
    before = db.scalar("SELECT COUNT(*) FROM invoices")
    with pytest.raises(BusinessError, match="Not enough stock"):
        trading.create_invoice(db, cust, [{"product_id": prod, "qty": 11, "price": 1}], paid=0)
    assert db.scalar("SELECT COUNT(*) FROM invoices") == before
    assert db.scalar("SELECT COUNT(*) FROM ledger WHERE ref_type='invoice'") == 0


def test_walkin_must_pay_in_full(shop):
    db, sup, cust, prod = _stocked(shop)
    walkin = db.scalar("SELECT id FROM parties WHERE is_walkin=1")
    with pytest.raises(BusinessError, match="pay in full"):
        trading.create_invoice(db, walkin, [{"product_id": prod, "qty": 1, "price": 50000}], paid=0)
    trading.create_invoice(db, walkin, [{"product_id": prod, "qty": 1, "price": 50000}], paid=50000)


def test_cancel_and_edit_invoice_reverse_correctly(shop):
    db, sup, cust, prod = _stocked(shop)
    inv = trading.create_invoice(db, cust, [{"product_id": prod, "qty": 3, "price": 50000}], paid=10000)
    trading.edit_invoice(db, inv, cust, [{"product_id": prod, "qty": 1, "price": 50000}], paid=50000)
    assert stock_qty(db.conn, prod) == 9
    assert customer_balance(db.conn, cust) == 0
    assert reports.cash_in_hand(db) == 50000
    trading.cancel_invoice(db, inv)
    assert stock_qty(db.conn, prod) == 10
    assert customer_balance(db.conn, cust) == 0
    assert reports.cash_in_hand(db) == 0
    assert reports.profit_loss(db, "2000-01-01", "2999-12-31")["net_sales"] == 0


# ---------- returns / payments ----------
def test_sale_return_and_over_return_blocked(shop):
    db, sup, cust, prod = _stocked(shop)
    inv = trading.create_invoice(db, cust, [{"product_id": prod, "qty": 2, "price": 50000}])
    trading.sale_return(db, cust, [{"product_id": prod, "qty": 1, "price": 50000}], ref_invoice_id=inv)
    assert stock_qty(db.conn, prod) == 9
    assert customer_balance(db.conn, cust) == 50000
    with pytest.raises(BusinessError, match="more than sold"):
        trading.sale_return(db, cust, [{"product_id": prod, "qty": 2, "price": 50000}], ref_invoice_id=inv)
    assert stock_qty(db.conn, prod) == 9  # failed return left no trace
    pl = reports.profit_loss(db, "2000-01-01", "2999-12-31")
    assert pl["gross_profit"] == 10000


def test_purchase_return(shop):
    db, sup, cust, prod = _stocked(shop)
    trading.purchase_return(db, sup, [{"product_id": prod, "qty": 4, "price": 40000}], received=60000)
    assert stock_qty(db.conn, prod) == 6
    assert supplier_balance(db.conn, sup) == 400000 - 160000 + 60000


def test_cash_recovery_expense_and_cashbook(shop):
    db, sup, cust, prod = _stocked(shop)
    trading.create_invoice(db, cust, [{"product_id": prod, "qty": 1, "price": 50000}])
    v = payments.receive_from_customer(db, cust, 20000, "partial")
    assert v.startswith("RV-")
    assert customer_balance(db.conn, cust) == 30000
    payments.add_expense(db, "Rent", 5000)
    payments.pay_supplier(db, sup, 100000)
    cb = reports.cash_book(db, "2000-01-01", "2999-12-31")
    assert cb["total_in"] == 20000 and cb["total_out"] == 105000 and cb["closing"] == -85000
    assert reports.profit_loss(db, "2000-01-01", "2999-12-31")["net_profit"] == 10000 - 5000


def test_balance_sheet_balances_with_reports(shop):
    db, sup, cust, prod = _stocked(shop)
    trading.create_invoice(db, cust, [{"product_id": prod, "qty": 2, "price": 50000}], paid=30000)
    bs = reports.balance_sheet(db)
    assert bs["stock_value"] == 8 * 40000
    assert bs["receivables"] == 70000
    assert bs["payables"] == 400000
    assert reports.all_balances(db, "customer")["rows"][0]["balance"] == 70000


# ---------- masters ----------
def test_search_exact_partial_tag_id_and_fuzzy(shop):
    db, *_ , prod = shop
    assert masters.search_products(db, "samsung")[0]["id"] == prod
    assert masters.search_products(db, "#mobile")[0]["id"] == prod
    assert masters.search_products(db, str(prod))[0]["id"] == prod
    assert masters.search_products(db, "samsng")[0]["id"] == prod  # misspelled


def test_soft_delete_when_used(shop):
    db, sup, cust, prod = _stocked(shop)
    trading.create_invoice(db, cust, [{"product_id": prod, "qty": 1, "price": 1}])
    assert masters.delete_party(db, cust) == "deactivated"
    assert masters.delete_product(db, prod) == "deactivated"
    unused = masters.add_party(db, "customer", "Temp")
    assert masters.delete_party(db, unused) == "deleted"


def test_serial_tracking(shop):
    db, sup, cust, _ = shop
    ph = masters.add_product(db, "iPhone 14", sale_price=250000, track_serial=True)
    trading.create_purchase(db, sup, [{"product_id": ph, "qty": 2, "price": 200000,
                                       "serials": ["IMEI1", "IMEI2"]}])
    inv = trading.create_invoice(db, cust, [{"product_id": ph, "qty": 1, "price": 250000, "serial": "IMEI1"}],
                                 paid=250000)
    with pytest.raises(BusinessError, match="not available"):
        trading.create_invoice(db, cust, [{"product_id": ph, "qty": 1, "price": 250000, "serial": "IMEI1"}])
    trading.cancel_invoice(db, inv)
    assert db.one("SELECT status FROM serials WHERE serial='IMEI1'")["status"] == "in_stock"


# ---------- branding for the login screen ----------
def test_branding_available_before_login(tmp_path):
    from app.services.auth import read_branding
    db = auth.register(tmp_path, "Burhan Nexus", "Main Road", "03001234567", "a@b.com",
                       None, "admin", PW, PW)
    assert read_branding(tmp_path)["name"] == "Burhan Nexus"
    masters.update_company(db, "Burhan Nexus Mobiles", "Main Road", "03001234567", "a@b.com")
    assert read_branding(tmp_path)["name"] == "Burhan Nexus Mobiles"
    db.close()


# ---------- menu structure (matches the requested layout) ----------
def test_menu_spec_matches_requirements():
    from app.ui.menu_spec import HOME_BUTTONS, MENUS, all_keys
    assert [t for t, _ in MENUS] == ["New Account", "Sale/Purchase", "Payments/Receipts",
                                     "Account Transactions", "Reports", "Utilities"]
    assert [len(i) for _, i in MENUS] == [4, 4, 4, 3, 9, 4]
    assert len(HOME_BUTTONS) == 7
    assert HOME_BUTTONS[0][0] == "Sale Invoice"
    assert len(all_keys()) == len(set(all_keys())) + 5  # a few keys are shared by design


def test_product_edit_rejects_blank_name(shop):
    db, _, _, prod = shop
    with pytest.raises(BusinessError, match="required"):
        masters.update_product(db, prod, name="   ")
    assert db.one("SELECT name FROM products WHERE id=?", (prod,))["name"] == "Samsung A15"
    masters.update_product(db, prod, name="Samsung A16", sale_price=55000)
    assert db.one("SELECT sale_price FROM products WHERE id=?", (prod,))["sale_price"] == 55000


# ---------- invoice PDF ----------
def test_invoice_pdf_a4_and_thermal(shop, tmp_path):
    from app.reports.invoice_pdf import build_invoice_pdf
    db, sup, cust, prod = _stocked(shop)
    inv = trading.create_invoice(db, cust, [{"product_id": prod, "qty": 2, "price": 50000}],
                                 discount=500, paid=20000, note="Warranty 1 year. شکریہ")
    for size in ("A4", "80mm"):
        out = build_invoice_pdf(db, inv, tmp_path / f"inv_{size}.pdf", size)
        data = open(out, "rb").read()
        assert data.startswith(b"%PDF") and len(data) > 1500


def test_register_with_logo_creates_folder(tmp_path):
    from PIL import Image
    logo = tmp_path / "src.png"
    Image.new("RGB", (50, 50), (10, 100, 200)).save(logo)
    data = tmp_path / "data"
    data.mkdir()
    db = auth.register(data, "X Shop", "Addr", "03001234567", "a@b.com", str(logo), "u", PW, PW)
    assert (data / "logo" / "logo.png").exists()
    db.close()


# ---------- invoice draft (screen logic) ----------
def test_invoice_draft_totals_profit_and_stock_warning(shop):
    from app.ui.invoice_model import InvoiceDraft
    db, sup, cust, prod = _stocked(shop)
    p = masters.search_products(db, "samsung")[0]
    d = InvoiceDraft()
    d.add_product(p)
    d.add_product(p)                       # same product again -> qty 2, one line
    assert len(d.lines) == 1 and d.lines[0]["qty"] == 2
    d.lines[0]["price"] = 50000
    d.lines[0]["discount"] = 1000
    d.discount = 500
    assert d.subtotal() == 99000 and d.total() == 98500
    assert d.profit() == 98500 - 80000
    assert d.over_stock() == []
    d.lines[0]["qty"] = 11
    assert len(d.over_stock()) == 1
    d.lines[0]["qty"] = 2
    inv = trading.create_invoice(db, cust, d.service_items(), discount=d.discount, paid=0)
    assert trading.invoice_profit(db, inv) == d.profit()


def test_purchase_and_voucher_pdfs(shop, tmp_path):
    from app.reports.doc_pdf import build_purchase_pdf, build_voucher_pdf
    db, sup, cust, prod = shop
    pid = trading.create_purchase(db, sup, [{"product_id": prod, "qty": 3, "price": 40000}], paid=50000,
                                  note="Lot 1")
    assert open(build_purchase_pdf(db, pid, tmp_path / "p.pdf"), "rb").read().startswith(b"%PDF")
    v = payments.pay_supplier(db, sup, 10000, "advance")
    assert open(build_voucher_pdf(db, v, tmp_path / "v.pdf"), "rb").read().startswith(b"%PDF")
    r = payments.receive_from_customer(db, cust, 500)
    assert open(build_voucher_pdf(db, r, tmp_path / "r.pdf"), "rb").read().startswith(b"%PDF")


def test_purchase_draft_requires_typed_price(shop):
    from app.ui.purchase_model import PurchaseDraft
    db, sup, cust, prod = shop
    p = masters.search_products(db, "samsung")[0]
    d = PurchaseDraft()
    ln = d.add_product(p)
    assert ln["price"] is None and len(d.missing_prices()) == 1   # never auto-filled
    ln["price"], ln["qty"] = 41000, 3
    assert d.total() == 123000 and not d.missing_prices()
    pid = trading.create_purchase(db, sup, d.service_items(), paid=23000)
    assert supplier_balance(db.conn, sup) == 100000 and stock_qty(db.conn, prod) == 3
    ph = masters.add_product(db, "iPhone 15", track_serial=True)
    d2 = PurchaseDraft()
    l2 = d2.add_product(masters.search_products(db, "iphone")[0], ["A1", "A2"])
    assert l2["qty"] == 2 and not d2.serial_mismatch()
    l2["qty"] = 3
    assert len(d2.serial_mismatch()) == 1


# ---------- report builders + exports ----------
def test_cash_book_balance_sheet_vouchers_and_exports(shop, tmp_path):
    from app.reports import builders, export
    db, sup, cust, prod = _stocked(shop)
    trading.create_invoice(db, cust, [{"product_id": prod, "qty": 2, "price": 50000}], paid=30000)
    payments.receive_from_customer(db, cust, 10000, "recovery")
    payments.add_expense(db, "Rent", 5000)
    cb = builders.cash_book_report(db, "2000-01-01", "2999-12-31")
    assert cb["rows"][0][1] == "Opening balance"
    assert cb["rows"][-1][-1] == "35,000.00"          # 30000 + 10000 - 5000
    assert cb["summary"][3] == ("Closing", "35,000.00")
    bs = builders.balance_sheet_report(db)
    # cash 35,000 + stock 8 x 40,000 + receivables (100,000 - 30,000 - 10,000) vs payables 400,000
    assert bs["summary"] == [("Total assets", "415,000.00"), ("Total liabilities", "400,000.00"),
                             ("Equity", "15,000.00")]
    vr = builders.vouchers_report(db, "2000-01-01", "2999-12-31")
    assert len(vr["rows"]) == 1 and vr["rows"][0][2] == "Receipt"
    co = masters.get_company(db)
    export.export_csv(cb, tmp_path / "cb.csv")
    export.export_xlsx(cb, tmp_path / "cb.xlsx")
    export.build_table_pdf(cb, co, tmp_path / "cb.pdf")
    assert open(tmp_path / "cb.pdf", "rb").read().startswith(b"%PDF")
    import openpyxl
    ws = openpyxl.load_workbook(tmp_path / "cb.xlsx").active
    assert ws["A1"].value == "Cash Book"
    assert "Opening balance" in open(tmp_path / "cb.csv", encoding="utf-8-sig").read()


def test_returnable_items_and_purchase_return_limit(shop):
    db, sup, cust, prod = shop
    pur = trading.create_purchase(db, sup, [{"product_id": prod, "qty": 10, "price": 40000}])
    inv = trading.create_invoice(db, cust, [{"product_id": prod, "qty": 4, "price": 50000, "discount": 4000}])
    r = trading.returnable_items(db, "sale", inv)[0]
    assert r["sold_qty"] == 4 and r["remaining"] == 4 and r["price"] == 49000   # discount spread per piece
    trading.sale_return(db, cust, [{"product_id": prod, "qty": 1, "price": r["price"]}], ref_invoice_id=inv)
    assert trading.returnable_items(db, "sale", inv)[0]["remaining"] == 3
    trading.purchase_return(db, sup, [{"product_id": prod, "qty": 2, "price": 40000}], ref_purchase_id=pur)
    assert stock_qty(db.conn, prod) == 10 - 4 + 1 - 2
    # a product with big opening stock: stock is fine, but the return exceeds what this purchase bought
    big = masters.add_product(db, "USB Cable", opening_stock=20)
    p2 = trading.create_purchase(db, sup, [{"product_id": big, "qty": 3, "price": 100}])
    with pytest.raises(BusinessError, match="more than bought"):
        trading.purchase_return(db, sup, [{"product_id": big, "qty": 5, "price": 100}], ref_purchase_id=p2)
    with pytest.raises(BusinessError, match="not on the selected purchase"):
        trading.purchase_return(db, sup, [{"product_id": prod, "qty": 1, "price": 100}], ref_purchase_id=p2)
    assert stock_qty(db.conn, big) == 23


def test_return_draft_rules(shop):
    from app.ui.return_model import ReturnDraft
    db, sup, cust, prod = _stocked(shop)
    inv = trading.create_invoice(db, cust, [{"product_id": prod, "qty": 3, "price": 50000}])
    d = ReturnDraft("sale")
    d.load_from_document(trading.returnable_items(db, "sale", inv))
    assert d.problems() == ["Enter a return quantity for at least one product."]
    d.lines[0]["qty"] = 5
    assert "only 3" in d.problems()[0]
    d.lines[0]["qty"] = 2
    assert d.problems() == [] and d.total() == 100000
    trading.sale_return(db, cust, d.service_items(), 0, inv)
    assert stock_qty(db.conn, prod) == 9
    m = ReturnDraft("purchase")
    ln = m.add_manual(masters.search_products(db, "samsung")[0])
    assert ln["price"] is None and "Type the price" in m.problems()[0]   # supplier price must be typed


def test_all_report_builders(shop):
    from app.reports import builders as B
    db, sup, cust, prod = _stocked(shop)
    inv = trading.create_invoice(db, cust, [{"product_id": prod, "qty": 2, "price": 50000}], paid=30000)
    payments.receive_from_customer(db, cust, 10000, "recovery")
    payments.add_expense(db, "Rent", 5000)
    f, t = "2000-01-01", "2999-12-31"
    ct = B.customer_transactions_report(db, f, t, cust)
    assert ct["rows"][-1][-1] == "60,000.00" and ct["summary"][0] == ("Closing balance", "60,000.00")
    assert B.customer_transactions_report(db, f, t, None)["headers"] == ["Select a customer above"]
    cr = B.cash_received_report(db, f, t)
    assert cr["summary"] == [("Total received", "40,000.00")]
    pl = B.profit_loss_report(db, f, t)
    assert pl["summary"] == [("Net profit", "15,000.00")]       # (100,000-80,000) - 5,000 rent
    iw = B.invoice_wise_report(db, f, t)
    assert iw["rows"][0][0] == "INV-00001" and iw["rows"][0][-1] == "20,000.00"
    sp = B.stock_position_report(db)
    assert sp["summary"][2] == ("Stock value", "320,000.00")
    pled = B.product_ledger_report(db, f, t, prod)
    assert pled["rows"][-1][-1] == "8" and pled["summary"] == [("Current stock", "8")]
    assert B.all_customer_balance_report(db)["summary"][1] == ("Total", "60,000.00")
    out = B.outstanding_report(db)
    assert ("Total To Receive", "60,000.00") in out["summary"] and ("Total To Pay", "400,000.00") in out["summary"]
    assert B.sale_summary_report(db, f, t)["summary"] == [("Total sales", "100,000.00")]
    assert B.products_report(db)["summary"] == [("Products", "1")]
    il = B.invoice_list_report(db, f, t)
    assert il["rows"][0][0] == "INV-00001" and il["rows"][0][-1] == "Active"
    trading.cancel_invoice(db, inv)
    assert B.invoice_list_report(db, f, t)["rows"][0][-1] == "Cancelled"


def test_customer_transactions_date_window(shop):
    from app.reports import builders as B
    db, sup, cust, prod = _stocked(shop)
    trading.create_invoice(db, cust, [{"product_id": prod, "qty": 1, "price": 50000}], date="2026-01-10 10:00:00")
    payments.receive_from_customer(db, cust, 20000, "", "2026-02-05 10:00:00")
    rep = B.customer_transactions_report(db, "2026-02-01", "2026-02-28", cust)
    assert rep["rows"][0][-1] == "50,000.00"            # balance before February
    assert rep["rows"][-1][-1] == "30,000.00" and len(rep["rows"]) == 3


def test_ledger_period_with_no_entries_in_window(shop):
    from app.reports import builders as B
    db, sup, cust, prod = _stocked(shop)
    trading.create_invoice(db, cust, [{"product_id": prod, "qty": 1, "price": 50000}], date="2026-01-10 10:00:00")
    rep = B.customer_transactions_report(db, "2026-03-01", "2026-03-31", cust)
    assert len(rep["rows"]) == 2                       # just opening + closing
    assert rep["rows"][0][-1] == "50,000.00" and rep["rows"][-1][-1] == "50,000.00"
    sup_rep = B.customer_transactions_report(db, "2000-01-01", "2999-12-31", sup)
    assert sup_rep["title"] == "Supplier Transactions" and sup_rep["rows"][-1][-1] == "400,000.00"


def _import_with_qt_stub(module):
    """Import a UI module even where PySide6 is not installed (stubs Qt just for the import)."""
    import importlib
    import sys
    from unittest.mock import MagicMock
    try:
        import PySide6  # noqa: F401
        return importlib.import_module(module)
    except ImportError:
        pass
    added = [n for n in ("PySide6", "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets") if n not in sys.modules]
    for n in added:
        sys.modules[n] = MagicMock()
    try:
        return importlib.import_module(module)
    finally:
        for n in added:
            sys.modules.pop(n, None)
        for n in [m for m in sys.modules if m.startswith("app.ui.")]:
            sys.modules.pop(n, None)


def test_every_menu_key_has_a_screen():
    from app.ui.menu_spec import all_keys
    modules = _import_with_qt_stub("app.ui.modules")
    missing = sorted(set(all_keys()) - set(modules.MODULES))
    assert missing == [], missing


# ---------- backup / restore ----------
def test_backup_restore_roundtrip(tmp_path):
    from app.services import backup
    data = tmp_path / "data"
    data.mkdir()
    db = auth.register(data, "Shop", "Addr", "03001234567", "a@b.com", None, "admin", PW, PW)
    masters.add_party(db, "customer", "Before Backup")
    out = backup.create_backup(db)
    assert out.exists() and out.suffix == ".bmbak"
    raw = out.read_bytes()
    assert b"Before Backup" not in raw and b"SQLite format" not in raw      # backup stays encrypted
    masters.add_party(db, "customer", "After Backup")
    safety = backup.restore_backup(db, out)
    assert safety.name.startswith("before_restore")
    db2 = auth.login(data, "admin", PW)
    names = [p["name"] for p in masters.search_parties(db2, "customer", "")]
    assert "Before Backup" in names and "After Backup" not in names
    db2.close()
    # the safety backup still holds the newer data
    back = tmp_path / "safety_data"
    back.mkdir()
    import zipfile
    zipfile.ZipFile(safety).extractall(back)
    db3 = Database(back, PW)
    assert "After Backup" in [r["name"] for r in db3.query("SELECT name FROM parties")]
    db3.close()


def test_restore_rejects_bad_files_and_auto_backup(tmp_path):
    from app.services import backup
    data = tmp_path / "d"
    data.mkdir()
    db = auth.register(data, "Shop", "Addr", "03001234567", "a@b.com", None, "admin", PW, PW)
    junk = tmp_path / "junk.bmbak"
    junk.write_bytes(b"not a zip")
    with pytest.raises(BusinessError, match="not a valid backup"):
        backup.restore_backup(db, junk)
    import zipfile
    empty = tmp_path / "empty.bmbak"
    with zipfile.ZipFile(empty, "w") as z:
        z.writestr("hello.txt", "x")
    with pytest.raises(BusinessError, match="incomplete"):
        backup.restore_backup(db, empty)
    assert db.conn is not None                                  # a rejected restore leaves the DB open
    usb = tmp_path / "usb"
    usb.mkdir()
    backup.save_settings(data, auto_backup=True, extra_folder=str(usb))
    out = backup.auto_backup_on_exit(db)
    assert out and out.name.startswith("auto_") and (usb / out.name).exists()
    backup.save_settings(data, auto_backup=False)
    assert backup.auto_backup_on_exit(db) is None
    assert len(backup.list_backups(data)) == 1
    db.close()
