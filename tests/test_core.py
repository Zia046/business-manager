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
    prod = masters.add_product(db, "Samsung A15", sale_price=50000, purchase_price=0, tags="#mobile",
                               category="Other")
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
    assert [len(i) for _, i in MENUS] == [6, 6, 4, 3, 14, 8]
    assert len(HOME_BUTTONS) == 8 and HOME_BUTTONS[-1][1] == "dashboard"
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
    assert ln["price"] is None and len(d.missing_prices()) == 1   # no saved price yet: it must be typed
    ln["price"], ln["qty"] = 41000, 3
    assert d.total() == 123000 and not d.missing_prices()
    pid = trading.create_purchase(db, sup, d.service_items(), paid=23000)
    assert supplier_balance(db.conn, sup) == 100000 and stock_qty(db.conn, prod) == 3
    ph = masters.add_product(db, "iPhone 15", category="Mobile Phone", imei_mode="single")
    d2 = PurchaseDraft()
    l2 = d2.add_product(masters.search_products(db, "iphone")[0], [("111111111111111", None), ("222222222222222", None)])
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
    big = masters.add_product(db, "USB Cable", opening_stock=20, category="Accessories")
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
    assert out["summary"] == [("Customers", "1"), ("Total to receive", "60,000.00")]
    assert not any("supplier" in str(r).lower() for r in out["rows"])        # suppliers are never listed
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
    db3 = Database(back, PW, login_id="admin")
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


# ================= phones, IMEI, categories =================
I1, I2, I3, I4 = "356938035643809", "356938035643817", "490154203237518", "490154203237526"


@pytest.fixture
def phones(shop):
    db, sup, cust, _ = shop
    single = masters.add_product(db, "Nokia 105", sale_price=5000, category="Mobile Phone", imei_mode="single")
    double = masters.add_product(db, "Samsung A55", sale_price=90000, category="Mobile Phone", imei_mode="double")
    trading.create_purchase(db, sup, [
        {"product_id": single, "qty": 2, "price": 4000, "serials": [I1, "111111111111111"]},
        {"product_id": double, "qty": 1, "price": 80000, "serials": [(I3, I4)]}])
    return db, sup, cust, single, double


def test_imei_rules():
    from app.services import imei
    assert imei.unit(" " + I1 + " ", None, "single") == (I1, None)
    for bad in ("12345", "1234567890a", "", "1" * 101):
        with pytest.raises(BusinessError):
            imei.unit(bad, None, "single")
    assert imei.unit("1" * 10, None, "single") and imei.unit("1" * 100, None, "single")   # 10 and 100 digits are fine
    with pytest.raises(BusinessError, match="cannot be the same"):
        imei.unit(I1, I1, "double")
    with pytest.raises(BusinessError, match="IMEI 2 is required"):
        imei.unit(I1, "", "double")
    with pytest.raises(BusinessError, match="single IMEI"):
        imei.unit(I1, I2, "single")
    assert imei.parse_lines(f"{I1}\n\n{I2}\n", "single") == [(I1, None), (I2, None)]
    assert imei.parse_lines(f"{I1} {I2}\n{I3},{I4}", "double") == [(I1, I2), (I3, I4)]
    with pytest.raises(BusinessError, match="Line 2"):
        imei.parse_lines(f"{I1} {I2}\n{I3}", "double")
    with pytest.raises(BusinessError, match="typed twice"):
        imei.parse_lines(f"{I1}\n{I1}", "single")


def test_category_rules(shop):
    db, *_ = shop
    names = [c["name"] for c in masters.list_categories(db)]
    assert names == ["Mobile Phone", "Accessories", "Contagious", "Disposable", "Other"]
    with pytest.raises(BusinessError, match="category"):
        masters.add_product(db, "No Category")
    with pytest.raises(BusinessError, match="category"):
        masters.add_product(db, "Bad Category", category="Weapons")
    with pytest.raises(BusinessError, match="single or double"):
        masters.add_product(db, "Phone", category="Mobile Phone", imei_mode="")
    with pytest.raises(BusinessError, match="opening stock"):
        masters.add_product(db, "Phone", category="Mobile Phone", imei_mode="single", opening_stock=3)
    pid = masters.add_product(db, "Phone", category="mobile phone", imei_mode="double")
    p = db.one("SELECT * FROM products WHERE id=?", (pid,))
    assert p["track_serial"] == 1 and p["imei_mode"] == "double" and p["category"] == "Mobile Phone"
    acc = masters.add_product(db, "Cable", category="Accessories", imei_mode="double")
    assert db.one("SELECT track_serial, imei_mode FROM products WHERE id=?", (acc,)) == {"track_serial": 0, "imei_mode": "single"}
    new = masters.add_category(db, "Chargers")
    with pytest.raises(BusinessError, match="already exists"):
        masters.add_category(db, "chargers")
    masters.update_product(db, acc, category="Chargers")
    with pytest.raises(BusinessError, match=r"product\(s\) use"):
        masters.delete_category(db, new)                         # in use
    masters.update_product(db, acc, category="Other")
    masters.delete_category(db, new)
    system = [c for c in masters.list_categories(db) if c["name"] == "Mobile Phone"][0]
    with pytest.raises(BusinessError, match="built-in"):
        masters.delete_category(db, system["id"])
    with pytest.raises(BusinessError, match="Select a category"):
        masters.update_product(db, acc, category="")


def test_phone_purchase_requires_every_imei_and_no_duplicates(phones):
    db, sup, cust, single, double = phones
    assert stock_qty(db.conn, single) == 2 and stock_qty(db.conn, double) == 1
    with pytest.raises(BusinessError, match="IMEI of every phone"):
        trading.create_purchase(db, sup, [{"product_id": single, "qty": 2, "price": 1, "serials": [I2]}])
    with pytest.raises(BusinessError, match="IMEI of every phone"):
        trading.create_purchase(db, sup, [{"product_id": single, "qty": 1, "price": 1}])      # no IMEI at all
    with pytest.raises(BusinessError, match="already exists"):
        trading.create_purchase(db, sup, [{"product_id": single, "qty": 1, "price": 1, "serials": [I1]}])
    with pytest.raises(BusinessError, match="already exists"):    # I3 is IMEI 1 of the double phone
        trading.create_purchase(db, sup, [{"product_id": single, "qty": 1, "price": 1, "serials": [I3]}])
    with pytest.raises(BusinessError, match="already exists"):    # I4 is IMEI 2 of the double phone
        trading.create_purchase(db, sup, [{"product_id": double, "qty": 1, "price": 1, "serials": [(I2, I4)]}])
    with pytest.raises(BusinessError, match="cannot be the same"):
        trading.create_purchase(db, sup, [{"product_id": double, "qty": 1, "price": 1, "serials": [(I2, I2)]}])
    with pytest.raises(BusinessError, match="at least 10|between 10"):
        trading.create_purchase(db, sup, [{"product_id": single, "qty": 1, "price": 1, "serials": ["12345"]}])
    assert stock_qty(db.conn, single) == 2 and db.scalar("SELECT COUNT(*) FROM serials") == 3   # nothing half-saved


def test_phone_sale_needs_typed_imei_and_prints_both(phones):
    db, sup, cust, single, double = phones
    with pytest.raises(BusinessError, match="IMEI is required"):          # never picked automatically
        trading.create_invoice(db, cust, [{"product_id": single, "qty": 1, "price": 5000}], paid=5000)
    with pytest.raises(BusinessError, match="not in the stock record"):
        trading.create_invoice(db, cust, [{"product_id": single, "qty": 1, "price": 5000, "serial": I2}], paid=5000)
    with pytest.raises(BusinessError, match="IMEI 2 is required"):
        trading.create_invoice(db, cust, [{"product_id": double, "qty": 1, "price": 90000, "serial": I3}], paid=90000)
    with pytest.raises(BusinessError, match="do not match"):
        trading.create_invoice(db, cust, [{"product_id": double, "qty": 1, "price": 90000,
                                           "serial": I3, "serial2": I2}], paid=90000)
    inv = trading.create_invoice(db, cust, [
        {"product_id": single, "qty": 1, "price": 5000, "serial": I1},
        {"product_id": double, "qty": 1, "price": 90000, "serial": I4, "serial2": I3}], paid=95000)   # swapped order is fine
    from app.services import reports as R
    items = {i["product_id"]: i for i in R.invoice_detail(db, inv)["items"]}
    assert (items[single]["serial"], items[single]["serial2"]) == (I1, None)
    assert (items[double]["serial"], items[double]["serial2"]) == (I3, I4)       # both IMEIs go on the bill
    with pytest.raises(BusinessError, match="already sold"):
        trading.create_invoice(db, cust, [{"product_id": single, "qty": 1, "price": 5000, "serial": I1}], paid=5000)
    with pytest.raises(BusinessError, match="own line"):
        trading.create_invoice(db, cust, [{"product_id": single, "qty": 2, "price": 5000, "serial": "111111111111111"}], paid=0)
    trading.cancel_invoice(db, inv)
    assert db.scalar("SELECT COUNT(*) FROM serials WHERE status='in_stock'") == 3


def test_same_imei_twice_on_one_invoice_rejected(phones):
    db, sup, cust, single, double = phones
    with pytest.raises(BusinessError, match="already sold"):
        trading.create_invoice(db, cust, [{"product_id": single, "qty": 1, "price": 1, "serial": I1},
                                          {"product_id": single, "qty": 1, "price": 1, "serial": I1}], paid=0)
    assert stock_qty(db.conn, single) == 2


def test_phone_return_by_imei(phones):
    db, sup, cust, single, double = phones
    inv = trading.create_invoice(db, cust, [{"product_id": single, "qty": 1, "price": 5000, "serial": I1}], paid=0)
    with pytest.raises(BusinessError, match="IMEI is required"):
        trading.sale_return(db, cust, [{"product_id": single, "qty": 1, "price": 5000}], ref_invoice_id=inv)
    with pytest.raises(BusinessError, match="was not sold"):
        trading.sale_return(db, cust, [{"product_id": single, "qty": 1, "price": 5000,
                                        "serial": "111111111111111"}], ref_invoice_id=inv)
    trading.sale_return(db, cust, [{"product_id": single, "qty": 1, "price": 5000, "serial": I1}], ref_invoice_id=inv)
    assert db.one("SELECT status FROM serials WHERE serial=?", (I1,))["status"] == "in_stock"
    assert stock_qty(db.conn, single) == 2
    # back to the supplier: the phone leaves the stock records completely
    trading.purchase_return(db, sup, [{"product_id": double, "qty": 1, "price": 80000, "serial": I3, "serial2": I4}])
    assert db.scalar("SELECT COUNT(*) FROM serials WHERE serial=?", (I3,)) == 0 and stock_qty(db.conn, double) == 0


def test_migration_from_old_database():
    import sqlite3
    from app.db.connection import _dict_factory
    from app.db.schema import migrate
    conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.row_factory = _dict_factory
    conn.executescript("""
        CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT, track_serial INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE serials (id INTEGER PRIMARY KEY, product_id INTEGER, serial TEXT NOT NULL UNIQUE);
        CREATE TABLE invoice_items (id INTEGER PRIMARY KEY, serial TEXT);
        INSERT INTO products(name) VALUES ('Old product');
        INSERT INTO serials(product_id, serial) VALUES (1, '123456789012345');""")
    migrate(conn)
    migrate(conn)                                              # running twice is harmless
    assert conn.execute("SELECT imei_mode FROM products").fetchone()["imei_mode"] == "single"
    assert conn.execute("SELECT imei2 FROM serials").fetchone()["imei2"] is None
    assert conn.execute("SELECT serial2 FROM invoice_items").fetchall() == []
    assert conn.execute("SELECT COUNT(*) AS n FROM categories").fetchone()["n"] == 5
    assert conn.execute("PRAGMA user_version").fetchone()["user_version"] == 3
    assert conn.execute("SELECT COUNT(*) AS n FROM repairs").fetchone()["n"] == 0


def test_old_database_file_opens_and_upgrades(tmp_path):
    """A real encrypted DB whose categories table/columns are missing gets upgraded when opened."""
    db = auth.register(tmp_path, "Shop", "A", "03001234567", "a@b.com", None, "admin", PW, PW)
    db.conn.execute("DROP TABLE categories")
    db.conn.execute("PRAGMA user_version = 0")
    db._persist()
    db.close()
    db2 = auth.login(tmp_path, "admin", PW)
    assert len(masters.list_categories(db2)) == 5
    db2.close()


def test_phone_bill_pdf_contains_both_imeis(phones, tmp_path):
    from app.reports.invoice_pdf import build_invoice_pdf
    db, sup, cust, single, double = phones
    inv = trading.create_invoice(db, cust, [{"product_id": double, "qty": 1, "price": 90000, "serial": I3,
                                             "serial2": I4}], paid=90000)
    for size in ("A4", "80mm"):
        out = build_invoice_pdf(db, inv, tmp_path / f"{size}.pdf", size)
        import subprocess
        text = subprocess.run(["pdftotext", out, "-"], capture_output=True, text=True).stdout
        assert I3 in text and I4 in text and "IMEI 1" in text and "IMEI 2" in text, size


# ================= reset database =================
def test_reset_needs_reason_password_and_selection(env):
    path, db = env
    with pytest.raises(BusinessError, match="Select what"):
        reset_mod().reset_data(db, PW, "testing the reset", [])
    with pytest.raises(BusinessError, match="reason"):
        reset_mod().reset_data(db, PW, "  ", ["transactions"])
    with pytest.raises(BusinessError, match="reason"):
        reset_mod().reset_data(db, PW, "abc", ["transactions"])
    with pytest.raises(BusinessError, match="password is incorrect"):
        reset_mod().reset_data(db, "wrong-password", "testing the reset", ["transactions"])
    assert not (path / "reset_log.txt").exists()                  # nothing happened


def reset_mod():
    from app.services import reset
    return reset


def test_reset_transactions_keeps_accounts_and_products(shop):
    db, sup, cust, prod = _stocked(shop)
    trading.create_invoice(db, cust, [{"product_id": prod, "qty": 2, "price": 50000}], paid=1000)
    payments.add_expense(db, "Rent", 500)
    r = reset_mod().reset_data(db, PW, "start fresh after testing", ["transactions"])
    assert r["safety"].exists() and not r["factory"]
    assert db.scalar("SELECT COUNT(*) FROM invoices") == 0 and db.scalar("SELECT COUNT(*) FROM cash_book") == 0
    assert db.scalar("SELECT COUNT(*) FROM products") == 1 and db.scalar("SELECT COUNT(*) FROM parties") == 3
    assert stock_qty(db.conn, prod) == 0                          # back to the opening stock
    inv = trading.create_invoice(db, cust, [{"product_id": prod, "qty": 1, "price": 1}], allow_negative_stock=True)
    assert db.one("SELECT no FROM invoices WHERE id=?", (inv,))["no"] == "INV-00001"      # numbering restarts
    assert "start fresh" in (db.data_dir / "reset_log.txt").read_text()


def test_reset_products_and_customers_force_transactions(shop):
    db, sup, cust, prod = _stocked(shop)
    trading.create_invoice(db, cust, [{"product_id": prod, "qty": 1, "price": 50000}])
    assert reset_mod().expand(["customers"]) == {"customers", "transactions"}
    reset_mod().reset_data(db, PW, "remove customers only", ["customers"])
    assert db.scalar("SELECT COUNT(*) FROM parties WHERE kind='customer' AND is_walkin=0") == 0
    assert db.scalar("SELECT COUNT(*) FROM parties WHERE is_walkin=1") == 1       # walk-in customer stays
    assert db.scalar("SELECT COUNT(*) FROM products") == 1 and db.scalar("SELECT COUNT(*) FROM parties WHERE kind='supplier'") == 1
    reset_mod().reset_data(db, PW, "remove the products too", ["products", "suppliers"])
    assert db.scalar("SELECT COUNT(*) FROM products") == 0 and db.scalar("SELECT COUNT(*) FROM parties WHERE kind='supplier'") == 0


def test_reset_balances_clears_outstanding_with_adjustment(shop):
    from app.reports import builders as B
    db, sup, cust, prod = _stocked(shop)
    trading.create_invoice(db, cust, [{"product_id": prod, "qty": 2, "price": 50000}], paid=10000)
    masters.update_party(db, sup, "Phone Supplier", opening_balance=2500)
    assert customer_balance(db.conn, cust) == 90000
    reset_mod().reset_data(db, PW, "clear all baqayajat", ["balances"])
    assert customer_balance(db.conn, cust) == 0 and supplier_balance(db.conn, sup) == 0
    assert db.scalar("SELECT COUNT(*) FROM invoices") == 1                      # sales history kept
    assert B.outstanding_report(db)["summary"][1] == ("Total to receive", "0.00")


def test_factory_reset_erases_everything_and_login(env):
    path, db = env
    masters.add_party(db, "customer", "X")
    r = reset_mod().reset_data(db, PW, "selling this computer", ["factory"])
    assert r["factory"] and r["safety"].exists() and db.conn is None
    assert not auth.is_registered(path)                                          # registration screen will return
    assert not (path / "branding.json").exists()
    # the safety backup can bring everything back
    from app.services import backup
    db2 = auth.register(path, "New", "A", "03001234567", "a@b.com", None, "u2", "other-pass", "other-pass")
    backup.restore_backup(db2, r["safety"])
    assert auth.login(path, "admin", PW)


# ---------- invoice numbers for several open windows ----------
def test_invoice_numbers_reuse_skipped_number_same_day(shop):
    db, sup, cust, prod = _stocked(shop)
    item = [{"product_id": prod, "qty": 1, "price": 50000}]
    n1 = trading.suggest_invoice_no(db)
    assert n1 == "INV-00001"
    a = trading.suggest_invoice_no(db, {n1})                      # second window opens while first is open
    assert a == "INV-00002"
    b = trading.suggest_invoice_no(db, {n1, a})
    assert b == "INV-00003"
    # windows 1 and 3 are saved with the numbers they were given, window 2 is closed without saving
    i1 = trading.create_invoice(db, cust, item, no=n1)
    i3 = trading.create_invoice(db, cust, item, no=b)
    assert [db.scalar("SELECT no FROM invoices WHERE id=?", (i,)) for i in (i1, i3)] == [n1, b]
    # the skipped number goes to the next invoice (same date)
    assert trading.suggest_invoice_no(db) == "INV-00002"
    i2 = trading.create_invoice(db, cust, item, no="INV-00002")
    assert db.scalar("SELECT no FROM invoices WHERE id=?", (i2,)) == "INV-00002"
    assert trading.suggest_invoice_no(db) == "INV-00004"
    # plain create_invoice (no number given) continues after the highest number
    i4 = trading.create_invoice(db, cust, item)
    assert db.scalar("SELECT no FROM invoices WHERE id=?", (i4,)) == "INV-00004"


def test_skipped_invoice_number_not_reused_on_a_different_date(shop):
    db, sup, cust, prod = _stocked(shop)
    item = [{"product_id": prod, "qty": 1, "price": 50000}]
    trading.create_invoice(db, cust, item, no="INV-00001", date="2026-10-30 10:00:00")
    trading.create_invoice(db, cust, item, no="INV-00003", date="2026-10-31 10:00:00")
    assert trading.suggest_invoice_no(db, today="2026-10-31") == "INV-00004"   # gap sits between two dates
    assert trading.suggest_invoice_no(db, today="2026-10-30") == "INV-00004"


def test_number_taken_meanwhile_falls_back_to_next(shop):
    db, sup, cust, prod = _stocked(shop)
    item = [{"product_id": prod, "qty": 1, "price": 50000}]
    trading.create_invoice(db, cust, item, no="INV-00001")
    i = trading.create_invoice(db, cust, item, no="INV-00001")     # same number asked again
    assert db.scalar("SELECT no FROM invoices WHERE id=?", (i,)) == "INV-00002"


def test_documents_carry_software_contact_line(shop, tmp_path):
    import subprocess, shutil
    from app.reports.invoice_pdf import build_invoice_pdf
    from app.config import DEVELOPER_PHONE
    db, sup, cust, prod = _stocked(shop)
    inv = trading.create_invoice(db, cust, [{"product_id": prod, "qty": 1, "price": 50000}])
    if shutil.which("pdftotext"):
        for size in ("A4", "80mm"):
            out = build_invoice_pdf(db, inv, tmp_path / f"{size}.pdf", size)
            text = subprocess.run(["pdftotext", out, "-"], capture_output=True, text=True).stdout
            assert DEVELOPER_PHONE in text and "To buy this software" in text.replace("\n", " ")


def test_cash_recovery_khata_last_month(shop):
    from datetime import datetime, timedelta
    db, sup, cust, prod = _stocked(shop)
    old = (datetime.now() - timedelta(days=45)).strftime("%Y-%m-%d 10:00:00")
    trading.create_invoice(db, cust, [{"product_id": prod, "qty": 1, "price": 50000}], date=old)
    trading.create_invoice(db, cust, [{"product_id": prod, "qty": 1, "price": 50000}])
    since = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    led = reports.customer_ledger(db, cust, since, None)
    assert led["period_opening"] == 50000 and len(led["rows"]) == 1 and led["closing"] == 100000
    payments.receive_from_customer(db, cust, 30000)
    led = reports.customer_ledger(db, cust, since, None)
    assert led["closing"] == 70000 and len(led["rows"]) == 2


def test_cash_recovery_and_new_screens_compile():
    import py_compile
    for f in ("cash_recovery", "sale_invoice", "modules", "main_window", "stock_purchase"):
        py_compile.compile(f"app/ui/{f}.py", doraise=True)


# ---------- licence ----------
def _issue(machine_raw, expiry=None, private=None):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization as s
    from app.services import licensing
    private = private or Ed25519PrivateKey.generate()
    pub = private.public_key().public_bytes(s.Encoding.Raw, s.PublicFormat.Raw).hex()
    return licensing.encode_key(licensing.machine_code(machine_raw), expiry, private.sign), pub, private


def test_licence_key_works_only_on_its_computer(tmp_path):
    from app.services import licensing
    key, pub, _ = _issue("PC-A-GUID")
    assert licensing.read_key(key, "PC-A-GUID", pub)[0] is True
    ok, _, msg = licensing.read_key(key, "PC-B-GUID", pub)
    assert not ok and "different computer" in msg
    assert not licensing.read_key("AAAA-BBBB", "PC-A-GUID", pub)[0]
    assert not licensing.read_key(key.replace(key[5], "A" if key[5] != "A" else "B"), "PC-A-GUID", pub)[0]
    other_pub = _issue("x")[1]
    assert not licensing.read_key(key, "PC-A-GUID", other_pub)[0]       # not signed by the owner


def test_licence_activate_status_and_expiry(tmp_path):
    from datetime import date, timedelta
    from app.services import licensing
    today = date(2026, 11, 2)
    assert licensing.status(tmp_path, today)["valid"] is False           # nothing activated yet
    key, pub, priv = _issue("PC-A", today + timedelta(days=30))
    assert licensing.activate(tmp_path, "garbage", "PC-A", pub)[0] is False
    assert licensing.activate(tmp_path, f"  {key}\n", "PC-A", pub, today)[0] is True
    st = licensing.status(tmp_path, today, "PC-A", pub)
    assert st["valid"] and st["days_left"] == 30
    assert licensing.status(tmp_path, today + timedelta(days=31), "PC-A", pub)["valid"] is False
    # clock moved back after use is refused
    licensing.status(tmp_path, today + timedelta(days=20), "PC-A", pub)
    assert licensing.status(tmp_path, today, "PC-A", pub)["valid"] is False
    # copying the licence file to another computer does not work
    assert licensing.status(tmp_path, today + timedelta(days=20), "PC-B", pub)["valid"] is False


def test_licence_for_life_and_embedded_public_key(tmp_path):
    from datetime import date
    from app.services import licensing
    key, pub, _ = _issue("PC-A", None)
    licensing.activate(tmp_path, key, "PC-A", pub)
    st = licensing.status(tmp_path, date(2040, 1, 1), "PC-A", pub)
    assert st["valid"] and st["days_left"] is None
    assert len(licensing.PUBLIC_KEY_HEX) == 64 and licensing.machine_code().count("-") == 3


def test_keygen_tool_makes_a_key_the_app_accepts():
    import importlib.util
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization as s
    from app.services import licensing
    try:
        spec = importlib.util.spec_from_file_location("keygen_gui", "tools/keygen_gui.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    except ModuleNotFoundError:
        import pytest
        pytest.skip("tkinter not installed here")
    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key().public_bytes(s.Encoding.Raw, s.PublicFormat.Raw).hex()
    key = mod.make_key(priv, licensing.machine_code("PC-Z"), None)
    assert licensing.read_key(key, "PC-Z", pub)[0]


def test_installer_and_workflow_files_are_wired():
    iss = open("installer.iss", encoding="utf-8").read()
    for needle in ("desktopicon", "autoprograms", "uninstallexe", "assets\\app.ico", "InfoBeforeFile"):
        assert needle in iss
    wf = open(".github/workflows/build.yml", encoding="utf-8").read()
    assert "ISCC.exe" in wf and "KeyGenerator" in wf and "--onedir" in wf
    assert "license_private" not in wf


# ---------- printer settings ----------
def test_58mm_and_80mm_bills_and_test_receipt(shop, tmp_path):
    from app.reports.invoice_pdf import build_invoice_pdf
    from app.reports.test_page import build_test_receipt
    db, sup, cust, prod = _stocked(shop)
    inv = trading.create_invoice(db, cust, [{"product_id": prod, "qty": 1, "price": 50000}])
    for size in ("58mm", "80mm"):
        out = build_invoice_pdf(db, inv, tmp_path / f"{size}.pdf", size)
        assert open(out, "rb").read().startswith(b"%PDF")
    assert open(build_test_receipt(tmp_path, 58), "rb").read().startswith(b"%PDF")


def test_printing_goes_to_chosen_printer_or_viewer(shop, tmp_path, monkeypatch):
    from app.services import backup
    ui = _import_with_qt_stub("app.ui.printing")
    db, sup, cust, prod = _stocked(shop)
    opened, printed = [], []
    monkeypatch.setattr(ui, "open_file", lambda p: opened.append(str(p)))
    import types, sys
    fake = types.ModuleType("app.ui.direct_print")
    fake.direct_print = lambda p, name=None: printed.append(name)
    monkeypatch.setitem(sys.modules, "app.ui.direct_print", fake)
    s = backup.get_settings(db.data_dir)
    assert s["thermal_printer"] == "" and s["thermal_width"] == 80
    assert ui.deliver(db, tmp_path / "x.pdf", thermal=True) == "viewer" and len(opened) == 1
    backup.save_settings(db.data_dir, thermal_printer="XP-80C", a4_printer="__default__")
    assert ui.deliver(db, tmp_path / "x.pdf", thermal=True) == "printer" and printed == ["XP-80C"]
    assert ui.deliver(db, tmp_path / "x.pdf", thermal=False) == "printer" and printed[-1] is None
    fake.direct_print = lambda p, name=None: (_ for _ in ()).throw(RuntimeError("offline"))
    assert ui.deliver(db, tmp_path / "x.pdf", thermal=True) == "viewer"      # failure never loses the bill
    backup.save_settings(db.data_dir, thermal_width=58)
    assert ui.resolve_size(db, "Thermal") == "58mm" and ui.resolve_size(db, "A4") == "A4"


# ---------- phone-shop helpers: IMEI search, daily closing, dashboard ----------
def test_imei_lookup_daily_closing_dashboard(phones):
    from app.reports import builders as B
    db, sup, cust, single, double = phones
    trading.create_invoice(db, cust, [{"product_id": single, "qty": 1, "price": 5500, "serial": I1}], paid=5500)
    rep = B.imei_search_report(db, I1[3:9])
    row = rep["rows"][0]
    assert row[0] == I1 and row[3] == "SOLD" and row[9] == "5,500.00"
    assert row[4] == "Phone Supplier" and row[6].startswith("Ali") and row[7].startswith("INV-")
    assert B.imei_search_report(db, I3)["rows"][0][3] == "In stock"
    assert B.imei_search_report(db, I4)["rows"][0][1] == I4                   # IMEI 2 is searchable too
    assert B.imei_search_report(db, "12")["rows"] == []                  # too short: no search
    d = reports.dashboard(db)
    assert d["today_sales"] == 5500 and d["today_invoices"] == 1 and d["phones_in_stock"] == 2
    assert d["cash"] >= 5500
    rep = B.daily_closing_report(db, "2000-01-01", "2100-01-01")
    assert rep["rows"][-1][0] == "Total" and rep["rows"][-1][1] == 1 and rep["rows"][-1][2] == "5,500.00"


# ---------- audit log ----------
def test_audit_log_records_important_actions(shop):
    db, sup, cust, prod = _stocked(shop)
    inv = trading.create_invoice(db, cust, [{"product_id": prod, "qty": 1, "price": 50000}], paid=1000)
    payments.receive_from_customer(db, cust, 500)
    payments.add_expense(db, "Tea", 80)
    trading.cancel_invoice(db, inv)
    rows = db.query("SELECT action, detail FROM audit_log ORDER BY id")
    actions = [r["action"] for r in rows]
    for a in ("Product added", "Stock purchase", "Sale invoice created", "Cash received from customer",
              "Expense", "Sale invoice cancelled"):
        assert a in actions, a
    created = [r for r in rows if r["action"] == "Sale invoice created"][0]["detail"]
    assert created.startswith("INV-") and "50,000" not in created and "50000" in created
    recv = [r for r in rows if r["action"] == "Cash received from customer"][0]["detail"]
    assert "500" in recv and "Ali" in recv


# ---------- staff accounts / key slots ----------
def test_staff_login_with_own_password_and_owner_controls(tmp_path):
    from app.services import common
    db = auth.register(tmp_path, "Shop", "A", "03001234567", "a@b.com", None, "owner1", PW, PW)
    assert common.is_owner()
    with pytest.raises(BusinessError, match="owner"):
        auth.add_staff(db, "wrong-password", "Bilal", "bilal", "staffpw1")
    auth.add_staff(db, PW, "Bilal", "bilal", "staffpw1")
    with pytest.raises(BusinessError, match="already used"):
        auth.add_staff(db, PW, "Bilal 2", "bilal", "staffpw2")
    with pytest.raises(BusinessError, match="6 characters"):
        auth.add_staff(db, PW, "X", "x", "123")
    db.close()
    # staff opens the SAME database with his own password; owner password does not work for him
    staff = auth.login(tmp_path, "bilal", "staffpw1")
    assert not common.is_owner() and staff.user["role"] == "staff"
    with pytest.raises(BusinessError, match="owner"):
        auth.add_staff(staff, "staffpw1", "Evil", "evil", "evilpw12")
    staff.close()
    for who, pw in (("bilal", PW), ("owner1", "staffpw1"), ("nobody", PW)):
        with pytest.raises(BusinessError, match="Invalid"):
            auth.login(tmp_path, who, pw)
    # owner disables, resets, and changes his own password
    owner = auth.login(tmp_path, "owner1", PW)
    assert common.is_owner() and len(auth.list_users(owner)) == 2
    auth.set_staff_active(owner, PW, "bilal", False)
    with pytest.raises(BusinessError, match="Invalid"):
        auth.login(tmp_path, "bilal", "staffpw1")
    auth.set_staff_active(owner, PW, "bilal", True)
    auth.reset_staff_password(owner, PW, "bilal", "newstaff9")
    auth.change_credentials(owner, PW, "owner1", "ownerNEW1")
    owner.close()
    auth.login(tmp_path, "bilal", "newstaff9").close()
    auth.login(tmp_path, "owner1", "ownerNEW1").close()
    with pytest.raises(BusinessError):
        auth.login(tmp_path, "owner1", PW)
    # staff actions are tagged with his name in the audit log
    s = auth.login(tmp_path, "bilal", "newstaff9")
    masters.add_party(s, "customer", "By Staff")
    assert s.one("SELECT user FROM audit_log WHERE action='Party added' ORDER BY id DESC")["user"] == "bilal"
    s.close()
    common.set_current_user(None)


def test_old_database_without_key_slots_still_opens(tmp_path):
    db = auth.register(tmp_path, "Shop", "A", "03001234567", "a@b.com", None, "admin", PW, PW)
    db.close()
    (tmp_path / "keys.json").unlink()                    # what a database from the earlier version looks like
    db2 = auth.login(tmp_path, "admin", PW)              # opens with the old key rule and creates the slot
    db2.close()
    assert (tmp_path / "keys.json").exists()
    auth.login(tmp_path, "admin", PW).close()


# ---------- warranty ----------
def test_warranty_on_bill_and_imei_search(phones, tmp_path):
    import shutil, subprocess
    from datetime import date
    from app.reports import builders as B
    from app.reports.invoice_pdf import build_invoice_pdf
    from app.services.common import add_months
    assert add_months("2026-01-31", 1) == "2026-02-28" and add_months("2026-11-02", 12) == "2027-11-02"
    db, sup, cust, single, double = phones
    with pytest.raises(BusinessError, match="120"):
        masters.update_product(db, single, warranty_months=500)
    masters.update_product(db, single, warranty_months=12)
    inv = trading.create_invoice(db, cust, [{"product_id": single, "qty": 1, "price": 5500, "serial": I1}], paid=5500)
    assert db.scalar("SELECT warranty_months FROM invoice_items WHERE invoice_id=?", (inv,)) == 12
    masters.update_product(db, single, warranty_months=3)             # later change does not touch old bills
    assert db.scalar("SELECT warranty_months FROM invoice_items WHERE invoice_id=?", (inv,)) == 12
    row = B.imei_search_report(db, I1)["rows"][0]
    until = add_months(date.today().isoformat(), 12)
    assert until[:4] in row[10] and "valid" in row[10]
    assert B.imei_search_report(db, I3)["rows"][0][10] == ""          # not sold: no warranty text
    if shutil.which("pdftotext"):
        out = build_invoice_pdf(db, inv, tmp_path / "w.pdf", "A4")
        text = subprocess.run(["pdftotext", out, "-"], capture_output=True, text=True).stdout
        assert "Warranty: 12 month(s)" in text


# ---------- warranty ----------
def test_warranty_on_bill_and_imei_search(phones, tmp_path):
    import shutil, subprocess
    from datetime import date
    from app.reports import builders as B
    from app.reports.invoice_pdf import build_invoice_pdf
    from app.services.common import add_months
    assert add_months("2026-01-31", 1) == "2026-02-28" and add_months("2026-11-02", 12) == "2027-11-02"
    db, sup, cust, single, double = phones
    with pytest.raises(BusinessError, match="120"):
        masters.update_product(db, single, warranty_months=500)
    masters.update_product(db, single, warranty_months=12)
    inv = trading.create_invoice(db, cust, [{"product_id": single, "qty": 1, "price": 5500, "serial": I1}], paid=5500)
    assert db.scalar("SELECT warranty_months FROM invoice_items WHERE invoice_id=?", (inv,)) == 12
    masters.update_product(db, single, warranty_months=3)             # later change does not touch old bills
    assert db.scalar("SELECT warranty_months FROM invoice_items WHERE invoice_id=?", (inv,)) == 12
    row = B.imei_search_report(db, I1)["rows"][0]
    until = add_months(date.today().isoformat(), 12)
    assert until[:4] in row[10] and "valid" in row[10]
    assert B.imei_search_report(db, I3)["rows"][0][10] == ""          # not sold: no warranty text
    if shutil.which("pdftotext"):
        out = build_invoice_pdf(db, inv, tmp_path / "w.pdf", "A4")
        text = subprocess.run(["pdftotext", out, "-"], capture_output=True, text=True).stdout
        assert "Warranty: 12 month(s)" in text


# ---------- Excel / CSV import ----------
def test_import_products_and_parties_from_excel_and_csv(shop, tmp_path):
    from app.services import importer
    db, sup, cust, prod = shop
    tpl = tmp_path / "t.xlsx"
    importer.write_template(tpl, "products")
    rows = importer.read_rows(tpl)                                    # the template's two example rows
    assert [r["name"] for r in rows] == ["Samsung A15 128GB", "Fast Charger 25W"]
    csv_file = tmp_path / "p.csv"
    csv_file.write_text("Name,Category,Sale Price,Purchase Price,Opening Stock,Tags,Unit,Low Stock Level,Warranty Months\n"
                        "Charger 20W,Accessories,\"1,500\",900,10,#charger,pcs,2,6\n"
                        "Vivo Y18,Mobile Phone,30000,27000,5,#vivo,pcs,1,12\n"
                        "Bad Category Item,Gadgets,100,50,1,,,0,0\n"
                        ",Accessories,1,1,1,,,0,0\n"
                        "Charger 20W,Accessories,1,1,1,,,0,0\n"
                        "Cable,Accessories,abc,1,1,,,0,0\n", encoding="utf-8")
    rows = importer.read_rows(csv_file)
    dry = importer.import_products(db, rows, dry_run=True)
    assert [r["status"] for r in dry] == ["new", "new", "error", "error", "skip", "error"]
    assert db.scalar("SELECT COUNT(*) FROM products WHERE name='Charger 20W'") == 0     # a dry run saves nothing
    res = importer.import_products(db, rows)
    assert [r["status"] for r in res] == ["new", "new", "error", "error", "skip", "error"]
    ch = db.one("SELECT * FROM products WHERE name='Charger 20W'")
    assert ch["sale_price"] == 1500 and ch["opening_stock"] == 10 and ch["warranty_months"] == 6
    vivo = db.one("SELECT * FROM products WHERE name='Vivo Y18'")
    assert vivo["track_serial"] == 1 and vivo["opening_stock"] == 0           # phone stock must come with IMEIs
    assert "IMEI" in res[1]["message"]
    again = importer.import_products(db, rows)
    assert [r["status"] for r in again][:2] == ["skip", "skip"]                # importing twice adds nothing new
    pf = tmp_path / "c.csv"
    pf.write_text("Name,Phone,Address,Opening Balance\nZaid,0300,Buner,2500\nAli,0301,x,0\n", encoding="utf-8")
    res = importer.import_parties(db, importer.read_rows(pf), "customer")
    assert [r["status"] for r in res] == ["new", "skip"]                      # 'Ali' already exists in the fixture
    zaid = db.one("SELECT id FROM parties WHERE name='Zaid'")["id"]
    assert customer_balance(db.conn, zaid) == 2500
    wrong = tmp_path / "w.csv"
    wrong.write_text("Item,Price\nA,1\n", encoding="utf-8")
    with pytest.raises(BusinessError, match="columns"):
        importer.import_products(db, importer.read_rows(wrong))
    with pytest.raises(BusinessError, match="Excel"):
        importer.read_rows(tmp_path / "x.txt")


# ---------- qist (installments), repairs, WhatsApp ----------
def test_qist_plan_schedule_and_allocation(shop):
    from app.services import installments as I
    db, sup, cust, prod = _stocked(shop)
    inv = trading.create_invoice(db, cust, [{"product_id": prod, "qty": 1, "price": 60000}], paid=0)
    pid = I.create_plan(db, cust, 60000, 3, "2026-12-01", invoice_id=inv)
    sched = I.schedule(db, pid)
    assert [s["amount"] for s in sched] == [20000, 20000, 20000]
    assert [s["due_date"] for s in sched] == ["2026-12-01", "2027-01-01", "2027-02-01"]
    with pytest.raises(BusinessError, match="already has"):
        I.create_plan(db, cust, 1000, 2, "2026-12-01", invoice_id=inv)
    payments.receive_from_customer(db, cust, 25000)                   # any cash recovery counts automatically
    sched = I.schedule(db, pid)
    assert [s["paid"] for s in sched] == [20000, 5000, 0]
    due = I.due_list(db, today="2027-01-10")
    assert [(d["seq"], d["remaining"], d["days_late"]) for d in due] == [(2, 15000, 9), (3, 20000, -22)]
    with pytest.raises(BusinessError, match="already paid"):
        I.cancel_plan(db, pid)
    payments.receive_from_customer(db, cust, 35000)
    assert db.scalar("SELECT status FROM installment_plans WHERE id=?", (pid,)) == "closed"
    assert customer_balance(db.conn, cust) == 0


def test_qist_rules(shop):
    from app.services import installments as I
    db, sup, cust, prod = _stocked(shop)
    with pytest.raises(BusinessError, match="more than this customer owes"):
        I.create_plan(db, cust, 5000, 2, "2026-12-01")
    walkin = db.scalar("SELECT id FROM parties WHERE is_walkin=1")
    with pytest.raises(BusinessError, match="saved customer"):
        I.create_plan(db, walkin, 100, 2, "2026-12-01")
    trading.create_invoice(db, cust, [{"product_id": prod, "qty": 1, "price": 10000}])
    with pytest.raises(BusinessError, match="between 1 and 60"):
        I.create_plan(db, cust, 5000, 0, "2026-12-01")
    pid = I.create_plan(db, cust, 10000, 1, "2026-12-01")
    I.cancel_plan(db, pid)
    assert db.scalar("SELECT status FROM installment_plans WHERE id=?", (pid,)) == "cancelled"
    assert I.due_list(db) == []


def test_qist_report_and_dashboard(shop):
    from app.reports import builders as B
    from app.services import installments as I
    db, sup, cust, prod = _stocked(shop)
    trading.create_invoice(db, cust, [{"product_id": prod, "qty": 1, "price": 30000}])
    I.create_plan(db, cust, 30000, 3, "2020-01-01")                   # long overdue
    rep = B.qist_due_report(db)
    assert rep["rows"][0][0].startswith("QST-") and rep["rows"][0][6].startswith("LATE")
    assert reports.dashboard(db)["qist_overdue"] == 3


def test_repair_job_cash_and_profit(shop):
    from app.services import repairs
    db, sup, cust, prod = _stocked(shop)
    j = repairs.create_job(db, "Bilal", "03001234567", "Samsung A12", "Screen broken", estimate=4000, advance=1000)
    assert db.scalar("SELECT no FROM repairs WHERE id=?", (j,)) == "RJ-00001"
    assert reports.cash_in_hand(db) - db.scalar("SELECT opening_cash FROM company WHERE id=1") == 1000
    repairs.update_job(db, j, status="ready", charges=3500)
    with pytest.raises(BusinessError, match="more than the charges"):
        repairs.deliver(db, j, 3500, 1500, 3000)
    repairs.deliver(db, j, 3500, 1500, 2500)
    job = repairs.list_jobs(db)[0]
    assert job["status"] == "delivered" and job["received"] == 3500 and job["due"] == 0
    p = reports.profit_loss(db, "2000-01-01", "2100-01-01")
    assert p["repair_income"] == 3500 and p["repair_cost"] == 1500 and p["gross_profit"] == 2000
    with pytest.raises(BusinessError, match="cannot be changed"):
        repairs.update_job(db, j, status="received")


def test_repair_cancel_returns_advance_and_partial_payment(shop):
    from app.services import repairs
    db, sup, cust, prod = _stocked(shop)
    base = reports.cash_in_hand(db)
    a = repairs.create_job(db, "Ali", "", "Nokia", "No power", advance=500)
    repairs.cancel_job(db, a)
    assert reports.cash_in_hand(db) == base and repairs.list_jobs(db)[0]["status"] == "cancelled"
    b = repairs.create_job(db, "Sana", "", "Vivo", "Charging port", advance=0)
    repairs.deliver(db, b, 2000, 500, 500)                              # leaves 1500 due
    assert [x for x in repairs.list_jobs(db, "delivered")][0]["due"] == 1500
    repairs.receive_payment(db, b, 1500)
    assert repairs.list_jobs(db, "delivered")[0]["due"] == 0
    with pytest.raises(BusinessError, match="more than the amount"):
        repairs.receive_payment(db, b, 1)
    assert len(repairs.list_jobs(db, text="vivo")) == 1 and repairs.list_jobs(db, "open") == []


def test_whatsapp_numbers_and_messages(shop):
    from app.services import reminders
    db, sup, cust, prod = _stocked(shop)
    assert reminders.normalize_phone("0347-5093446") == "923475093446"
    assert reminders.normalize_phone("+92 347 5093446") == "923475093446"
    assert reminders.normalize_phone("3475093446") == "923475093446"
    assert reminders.normalize_phone("") == ""
    trading.create_invoice(db, cust, [{"product_id": prod, "qty": 1, "price": 7000}])
    phone, text = reminders.balance_message(db, cust)
    assert "7,000" in text and "Ali" in text
    assert reminders.whatsapp_url("03475093446", "hi there").startswith("https://wa.me/923475093446?text=hi%20there")
    assert reminders.qist_message(db, cust)[1] == ""                    # no plan, nothing to say


def test_reset_clears_qist_and_repairs(shop):
    from app.services import installments as I, repairs, reset
    db, sup, cust, prod = _stocked(shop)
    trading.create_invoice(db, cust, [{"product_id": prod, "qty": 1, "price": 9000}])
    I.create_plan(db, cust, 9000, 3, "2026-12-01")
    repairs.create_job(db, "Zed", "", "Itel", "x", advance=100)
    reset.reset_data(db, PW, "testing reset", ["customers"])
    assert db.scalar("SELECT COUNT(*) FROM installment_plans") == 0 and db.scalar("SELECT COUNT(*) FROM repairs") == 0


# ---------- barcode, labels, repair slip, price list ----------
def test_barcode_field_scan_search_and_uniqueness(shop):
    db, sup, cust, prod = shop
    a = masters.add_product(db, "USB Cable", sale_price=300, category="Accessories", barcode="8901234")
    assert masters.search_products(db, "8901234")[0]["id"] == a            # what a scanner types
    with pytest.raises(BusinessError, match="already used"):
        masters.add_product(db, "Other cable", sale_price=1, category="Accessories", barcode="8901234")
    with pytest.raises(BusinessError, match="letters and digits"):
        masters.add_product(db, "Bad", sale_price=1, category="Accessories", barcode="12 34")
    masters.update_product(db, a, barcode="")
    assert masters.search_products(db, f"{a:06d}")[0]["id"] == a           # label without barcode uses 6-digit ID
    assert masters.barcode_for({"id": 7, "barcode": None}) == "000007"


def test_labels_repair_slip_and_price_list_pdfs(shop, tmp_path):
    from app.reports import builders as B
    from app.reports.labels_pdf import build_labels_pdf
    from app.reports.repair_slip import build_repair_slip
    from app.services import repairs
    db, sup, cust, prod = shop
    for layout in ("sheet", "roll"):
        out = build_labels_pdf(db, [(prod, 30 if layout == "sheet" else 2)], tmp_path / f"{layout}.pdf", layout)
        assert open(out, "rb").read().startswith(b"%PDF")
    with pytest.raises(ValueError):
        build_labels_pdf(db, [(prod, 0)], tmp_path / "none.pdf")
    j = repairs.create_job(db, "Bilal", "0300", "Samsung", "Screen", estimate=3000, advance=500)
    for w in (80, 58):
        assert open(build_repair_slip(db, j, tmp_path / f"slip{w}.pdf", w), "rb").read().startswith(b"%PDF")
    rep = B.price_list_report(db)
    assert rep["headers"] == ["Category", "Product", "Unit", "Price"] and rep["rows"]


# ---------- backup while working, check, status ----------
def test_periodic_backup_verify_and_status(tmp_path):
    import time
    from app.services import backup
    data = tmp_path / "data"
    data.mkdir()
    db = auth.register(data, "Shop", "Addr", "03001234567", "a@b.com", None, "admin", PW, PW)
    assert backup.last_backup_info(data)["time"] is None
    with pytest.raises(BusinessError, match="no backup yet"):
        backup.verify_latest(data)
    first = backup.periodic_backup(db, every_minutes=120)
    assert first and first.exists() and backup.last_backup_info(data)["name"] == first.name
    assert backup.periodic_backup(db, every_minutes=120) is None                      # too soon
    masters.add_party(db, "customer", "New Customer")                                 # data changed ...
    assert backup.periodic_backup(db, every_minutes=120) is None                      # ... still too soon
    later = time.time() + 3 * 3600
    assert backup.periodic_backup(db, every_minutes=120, now_ts=later)                 # 3 hours later: backs up
    assert backup.verify_latest(data).startswith("OK")
    backup.save_settings(data, auto_backup=False)
    assert backup.periodic_backup(db, every_minutes=0, now_ts=later + 99999) is None  # switched off
    bad = tmp_path / "bad.bmbak"
    bad.write_bytes(b"not a zip")
    with pytest.raises(BusinessError):
        backup.verify_backup(bad)
    assert backup.removable_drives() == []                                           # not Windows here
    db.close()


def test_periodic_backup_copies_to_usb_folder(tmp_path):
    from app.services import backup
    data, usb = tmp_path / "data", tmp_path / "usb"
    data.mkdir()
    usb.mkdir()
    db = auth.register(data, "Shop", "Addr", "03001234567", "a@b.com", None, "admin", PW, PW)
    backup.save_settings(data, extra_folder=str(usb))
    out = backup.periodic_backup(db)
    assert (usb / out.name).exists()
    db.close()


def test_new_screens_compile_and_staff_can_use_them():
    import py_compile
    from app.services import permissions
    for f in ("qist_ui", "repairs_ui", "labels_ui", "whatsapp", "modules", "main_window", "report_screens",
              "backup_ui", "cash_recovery", "products"):
        py_compile.compile(f"app/ui/{f}.py", doraise=True)
    for key in ("qist", "repairs", "labels", "price_list", "qist_due"):
        assert permissions.can_open("staff", key)
    for key in ("profit_loss", "reset_db", "users", "audit_log", "backup"):
        assert not permissions.can_open("staff", key)


# ---------- dashboard graphs ----------
def test_dashboard_buckets_and_series(shop):
    from datetime import date
    db, sup, cust, prod = _stocked(shop)
    b = reports._buckets("daily", date(2026, 11, 3))
    assert len(b) == 14 and b[-1][:2] == (date(2026, 11, 3), date(2026, 11, 3)) and b[0][0] == date(2026, 10, 21)
    w = reports._buckets("weekly", date(2026, 11, 3))                     # Tuesday
    assert len(w) == 12 and w[-1][0] == date(2026, 11, 2) and w[-1][1] == date(2026, 11, 8)
    m = reports._buckets("monthly", date(2026, 2, 10))
    assert len(m) == 12 and m[-1][:2] == (date(2026, 2, 1), date(2026, 2, 28)) and m[0][0] == date(2025, 3, 1)
    assert m[0][2] == "Mar 25"
    y = reports._buckets("yearly", date(2026, 5, 5))
    assert [x[2] for x in y] == ["2022", "2023", "2024", "2025", "2026"]
    with pytest.raises(ValueError):
        reports._buckets("hourly", date(2026, 1, 1))
    trading.create_invoice(db, cust, [{"product_id": prod, "qty": 1, "price": 60000}], paid=60000)
    for period in ("daily", "weekly", "monthly", "yearly"):
        s = reports.dashboard_series(db, period)
        assert len(s["labels"]) == len(s["sales"]) == len(s["profit"])
        assert s["sales"][-1] == 60000 and s["total_sales"] == 60000
        assert s["profit"][-1] > 0 and s["total_profit"] == s["profit"][-1]


def test_dashboard_lists(shop):
    db, sup, cust, prod = _stocked(shop)
    trading.create_invoice(db, cust, [{"product_id": prod, "qty": 1, "price": 40000}])
    d = reports.dashboard_lists(db)
    assert d["recent"][0]["customer"] == "Ali" and d["debtors"][0]["balance"] == 40000
    assert isinstance(d["low_stock"], list) and d["due_dates"] == []


# ---------- dashboard graphs ----------
def test_sales_series_buckets(shop):
    from datetime import date
    db, sup, cust, prod = _stocked(shop)
    today = date(2026, 11, 3)                                   # a Tuesday
    item = lambda p: [{"product_id": prod, "qty": 1, "price": p}]
    trading.create_invoice(db, cust, item(1000), date="2026-11-03 10:00:00")
    trading.create_invoice(db, cust, item(2000), date="2026-11-02 10:00:00")     # Monday, same week
    trading.create_invoice(db, cust, item(4000), date="2026-10-20 10:00:00")
    trading.create_invoice(db, cust, item(8000), date="2025-03-05 10:00:00")
    day = reports.sales_series(db, "day", today)
    assert len(day) == 14 and day[-1] == ("3/11", 1000) and day[-2] == ("2/11", 2000)
    week = reports.sales_series(db, "week", today)
    assert len(week) == 8 and week[-1] == ("2/11", 3000)                          # Mon 2 Nov week
    month = reports.sales_series(db, "month", today)
    assert len(month) == 12 and month[-1] == ("Nov 26", 3000) and month[-2] == ("Oct 26", 4000)
    year = reports.sales_series(db, "year", today)
    assert [y[0] for y in year] == ["2022", "2023", "2024", "2025", "2026"]
    assert year[-1][1] == 7000 and year[-2][1] == 8000
    inv = trading.create_invoice(db, cust, item(500), date="2026-11-03 11:00:00")
    trading.cancel_invoice(db, inv)
    assert reports.sales_series(db, "day", today)[-1][1] == 1000                  # cancelled bills are not counted


def test_profit_series_and_extras(shop):
    from datetime import date
    db, sup, cust, prod = _stocked(shop)
    today = date(2026, 11, 3)
    trading.create_invoice(db, cust, [{"product_id": prod, "qty": 1, "price": 60000}], date="2026-11-01 09:00:00")
    payments.add_expense(db, "Rent", 5000, "", "2026-11-02 09:00:00")
    ps = reports.profit_series(db, today)
    assert len(ps) == 12 and ps[-1][0] == "Nov 26" and ps[-1][1] < 60000          # sale minus cost minus expense
    assert ps[0][1] == 0
    ex = reports.dashboard_extras(db, today)
    assert ex["month_sales"] == 60000 and ex["top_products"][0]["qty"] == 1
    assert ex["month_profit"] == ps[-1][1] and ex["year_profit"] == ps[-1][1]
    assert ex["open_repairs"] == 0 and isinstance(ex["low_items"], list)


def test_charts_render_pictures():
    from app.reports import charts
    img = charts.bar_chart([("a", 100), ("b", 0), ("c", 2500000)], "Sales", size=(400, 200))
    assert img.size == (400, 200) and len(img.getcolors(1000000)) > 5
    loss = charts.bar_chart([("a", -50), ("b", 80)], "P/L", size=(400, 200), signed=True)
    assert loss.getpixel((100, 100)) is not None
    assert charts.bar_chart([], "Empty", size=(300, 150)).size == (300, 150)      # no data: still a picture
    assert charts.clock_image(3, 15, 45, 120).size == (120, 120)
    assert charts.to_png(img).startswith(b"\x89PNG")
    assert [charts.short(v) for v in (800, 45500, 1250000, -12000)] == ["800", "45.5k", "1.25M", "-12k"]


def test_dashboard_and_main_window_modules_load():
    for name in ("app.ui.dashboard", "app.ui.main_window"):
        assert _import_with_qt_stub(name) is not None
    src = open("app/ui/main_window.py", encoding="utf-8").read()
    # the developer line is a plain, non-interactive label shown under every page
    assert "Developed by" in src and "NoTextInteraction" in src and "_build_footer" in src
    dash = open("app/ui/dashboard.py", encoding="utf-8").read()
    assert "Home Screen" in dash and "Profit / Loss per month" in dash and "QCalendarWidget" in dash


def test_purchase_price_comes_from_last_saved_price_and_can_change(shop):
    from app.ui.purchase_model import PurchaseDraft
    db, sup, cust, _ = shop
    prod = masters.add_product(db, "Earphones", sale_price=900, purchase_price=600, category="Accessories")
    p = masters.search_products(db, "earphones")[0]
    d = PurchaseDraft()
    ln = d.add_product(p)
    assert ln["price"] == 600 and ln["price_saved"] and not d.missing_prices()      # filled in, nothing to type
    ln["qty"] = 10
    assert d.total() == 6000
    ln["price"] = 650                                                              # the person changes it
    trading.create_purchase(db, sup, d.service_items(), paid=6500)
    p2 = masters.search_products(db, "earphones")[0]
    assert p2["last_purchase_price"] == 650                                        # next time 650 is suggested
    assert PurchaseDraft().add_product(p2)["price"] == 650
    assert stock_qty(db.conn, prod) == 10


def test_owner_can_set_cash_in_hand_with_password_but_staff_cannot(tmp_path):
    from app.services import cash, common, reports as R
    owner = auth.register(tmp_path, "Shop", "A", "03001234567", "a@b.com", None, "owner1", PW, PW)
    common.set_current_user({"login_id": "owner1", "role": "owner"})
    masters.add_party(owner, "customer", "Ali")
    assert R.cash_in_hand(owner) == 0
    with pytest.raises(BusinessError):
        cash.set_cash_in_hand(owner, 5000, "wrong-pw")                 # password is required
    assert cash.set_cash_in_hand(owner, 5000, PW, "counted drawer") == 5000
    assert R.cash_in_hand(owner) == 5000
    assert cash.set_cash_in_hand(owner, 3200.5, PW) == -1799.5         # can also go down
    assert R.cash_in_hand(owner) == 3200.5
    assert cash.set_cash_in_hand(owner, 3200.5, PW) == 0               # same amount: nothing posted
    with pytest.raises(BusinessError):
        cash.set_cash_in_hand(owner, -1, PW)
    rows = R.cash_book(owner, "2000-01-01", "2999-12-31")["rows"]
    assert [r["ref_type"] for r in rows] == ["cash_adjust", "cash_adjust"]          # old entries untouched
    assert owner.one("SELECT detail FROM audit_log WHERE action='Cash in Hand changed' ORDER BY id DESC")
    auth.add_staff(owner, PW, "Bilal", "bilal", "staffpw1")
    owner.close()
    s = auth.login(tmp_path, "bilal", "staffpw1")
    common.set_current_user({"login_id": "bilal", "role": "staff"})
    with pytest.raises(BusinessError):
        cash.set_cash_in_hand(s, 1, "staffpw1")                        # staff can never change it
    s.close()
    common.set_current_user(None)


def test_product_picker_rows_hide_purchase_price_from_staff(shop):
    from app.ui.picker_rows import picker_columns, picker_row
    db, sup, cust, prod = shop
    masters.add_product(db, "Charger", sale_price=500, purchase_price=320, category="Accessories")
    p = masters.search_products(db, "charger")[0]
    assert picker_columns(True)[-2:] == ["Last purchase price", "Average cost"]
    assert picker_row(p, True)[1] == "Charger" and picker_row(p, True)[5] == "320.00"
    assert picker_columns(False) == ["ID", "Product", "Category", "In stock", "Sale price"]
    assert "320.00" not in picker_row(p, False) and len(picker_row(p, False)) == 5


def test_last_sold_price_to_same_customer(shop):
    db, sup, cust, prod = shop
    trading.create_purchase(db, sup, [{"product_id": prod, "qty": 10, "price": 100}], paid=1000)
    assert trading.last_sold_prices(db, cust, [prod]) == {}                       # never sold yet
    a = trading.create_invoice(db, cust, [{"product_id": prod, "qty": 1, "price": 150}], paid=150)
    b = trading.create_invoice(db, cust, [{"product_id": prod, "qty": 2, "price": 160, "discount": 10}], paid=0)
    got = trading.last_sold_prices(db, cust, [prod])[prod]
    assert got["price"] == 160 and got["qty"] == 2 and got["discount"] == 10          # the latest bill
    assert trading.last_sold_prices(db, cust, [prod], exclude_invoice_id=b)[prod]["price"] == 150
    assert trading.last_sold_prices(db, 99999, [prod]) == {}                      # other customer: nothing


def test_slogan_is_editable_and_low_stock_report_lists_only_low_items(shop):
    from app.reports import builders as B
    db, sup, cust, prod = shop
    assert masters.get_company(db)["slogan"] == "Complete Business Management Solution"       # default for old shops too
    co = masters.get_company(db)
    masters.update_company(db, co["name"], co["address"], co["phone"], co["email"], None, "Smart Business")
    assert masters.get_company(db)["slogan"] == "Smart Business"
    masters.update_company(db, co["name"], co["address"], co["phone"], co["email"])          # slogan untouched
    assert masters.get_company(db)["slogan"] == "Smart Business"
    masters.update_company(db, co["name"], co["address"], co["phone"], co["email"], None, "")
    assert masters.get_company(db)["slogan"] == ""
    ok = masters.add_product(db, "Plenty", sale_price=100, purchase_price=50, category="Accessories", low_stock_level=2)
    trading.create_purchase(db, sup, [{"product_id": ok, "qty": 20, "price": 50}], paid=1000)
    rep = B.low_stock_report(db)
    names = [r[1] for r in rep["rows"]]
    assert "Plenty" not in names and rep["rows"]                          # well stocked: not listed
    assert all(r[6] in ("OUT OF STOCK", "LOW STOCK") for r in rep["rows"])
    assert not any("avg" in h.lower() or "cost" in h.lower() for h in rep["headers"])   # no cost figures
    from app.services import permissions
    assert permissions.can_open("staff", "low_stock")
