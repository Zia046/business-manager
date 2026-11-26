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
    assert [len(i) for _, i in MENUS] == [6, 9, 4, 3, 14, 12]
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
    assert conn.execute("PRAGMA user_version").fetchone()["user_version"] == 6
    assert conn.execute("SELECT COUNT(*) AS n FROM repairs").fetchone()["n"] == 0
    for table in ("used_phones", "loan_people", "loan_entries"):          # added later: old data is untouched
        assert conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"] == 0
    assert conn.execute("SELECT name FROM products").fetchone()["name"] == "Old product"


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


def test_low_stock_report_lists_only_low_items(shop):
    from app.reports import builders as B
    db, sup, cust, prod = shop
    ok = masters.add_product(db, "Plenty", sale_price=100, purchase_price=50, category="Accessories", low_stock_level=2)
    trading.create_purchase(db, sup, [{"product_id": ok, "qty": 20, "price": 50}], paid=1000)
    rep = B.low_stock_report(db)
    names = [r[1] for r in rep["rows"]]
    assert "Plenty" not in names and rep["rows"]                          # well stocked: not listed
    assert all(r[6] in ("OUT OF STOCK", "LOW STOCK") for r in rep["rows"])
    assert not any("avg" in h.lower() or "cost" in h.lower() for h in rep["headers"])   # no cost figures
    from app.services import permissions
    assert permissions.can_open("staff", "low_stock")


def test_generate_barcode_is_short_numeric_and_unique(shop):
    db, sup, cust, prod = shop
    seen = set()
    for _ in range(200):
        code = masters.generate_barcode(db)
        assert code.isdigit() and 5 <= len(code) <= 10 and code[0] != "0" and code not in seen
        seen.add(code)
    assert len(masters.generate_barcode(db, 5)) == 5 and len(masters.generate_barcode(db, 99)) == 10
    p = masters.add_product(db, "Cable", sale_price=100, purchase_price=50, category="Accessories",
                            barcode=masters.generate_barcode(db))
    q = masters.add_product(db, "Cable2", sale_price=100, purchase_price=50, category="Accessories",
                            barcode=masters.generate_barcode(db))
    a, b = (db.one("SELECT barcode FROM products WHERE id=?", (i,))["barcode"] for i in (p, q))
    assert a != b                                                    # every product has its own barcode
    assert masters.search_products(db, a)[0]["id"] == p              # a scanner finds it
    with pytest.raises(BusinessError):
        masters.update_product(db, q, barcode=a)                     # no sharing


def test_a4_barcode_page_layout_and_page_count(shop, tmp_path):
    from reportlab.lib.units import mm
    from app.reports.labels_pdf import build_labels_pdf, grid_layout
    db, sup, cust, prod = shop
    for n in (1, 2, 6, 12, 21, 30, 40, 65, 84):
        cols, rows, w, h = grid_layout(n)
        assert cols * rows >= n and w >= 28 * mm and h >= 15 * mm and cols * w <= 210 * mm
        assert rows * h <= 297 * mm
    out = tmp_path / "bc.pdf"
    build_labels_pdf(db, [(prod, 40)], out, "grid", per_page=12)               # 40 labels, 12 per page = 4 pages
    assert out.read_bytes().count(b"/Type /Page\n") + out.read_bytes().count(b"/Type /Page ") >= 4
    build_labels_pdf(db, [(prod, 3)], tmp_path / "roll.pdf", "roll")


def test_installer_build_includes_reportlab_barcode_modules():
    import pathlib
    root = pathlib.Path(__file__).resolve().parent.parent
    assert "--collect-submodules reportlab.graphics.barcode" in (root / ".github/workflows/build.yml").read_text()
    assert "--collect-submodules reportlab.graphics.barcode" in (root / "build_exe.bat").read_text()
    src = (root / "app/ui/barcode_print.py").read_text() + (root / "app/reports/labels_pdf.py").read_text()
    assert not any(l.startswith(("from reportlab.graphics", "import reportlab.graphics")) for l in src.splitlines())


def test_mobile_reminder_export_has_finished_messages(shop):
    import json
    from app.services import reminders
    db, sup, cust, prod = shop
    trading.create_purchase(db, sup, [{"product_id": prod, "qty": 5, "price": 100}], paid=500)
    cust = masters.add_party(db, "customer", "Bilal", phone="0347-5093446")
    trading.create_invoice(db, cust, [{"product_id": prod, "qty": 1, "price": 12500}], paid=0)
    nophone = masters.add_party(db, "customer", "NoPhone")
    trading.create_invoice(db, nophone, [{"product_id": prod, "qty": 1, "price": 100}], paid=0)
    data = reminders.mobile_export(db)
    assert data["version"] == 1 and data["no_phone"] == 1
    owing = [i for i in data["items"] if i["id"] == cust]
    assert len(owing) == 1
    m = owing[0]["message"]
    assert "12,500" in m and "xxxxxx" not in m and "*" not in m and "روپے" in m and owing[0]["amount"] == 12500
    assert owing[0]["phone"] == "03475093446"
    assert reminders.sms_text("Rs xxxxxx due xxxxxx", 1250.4) == "Rs 1,250 due 1,250"
    json.dumps(data, ensure_ascii=False)                          # can be written as a file


def test_dashboard_overview_and_recent_transactions(shop):
    db, sup, cust, prod = shop
    trading.create_purchase(db, sup, [{"product_id": prod, "qty": 10, "price": 100}], paid=400)
    trading.create_invoice(db, cust, [{"product_id": prod, "qty": 2, "price": 150}], paid=100)
    o = reports.dashboard_overview(db)
    assert o["month_sales"] == 300 and o["month_purchases"] == 1000
    assert o["receivable"] == 200 and o["payable"] == 600
    assert o["stock_units"] >= 8 and o["month_expenses"] == 0 and "month_profit" in o
    rows = reports.recent_transactions(db)
    assert {r["kind"] for r in rows} == {"Sale", "Purchase"} and rows[0]["amount"] in (300, 1000)
    assert {r["kind"] for r in reports.recent_transactions(db, include_purchases=False)} == {"Sale"}


def test_table_cell_editors_have_no_big_padding():
    """Typed digits were cut off because table cell editors inherited the 6px padding of normal input boxes."""
    import importlib.util, pathlib
    spec = importlib.util.spec_from_file_location("theme", pathlib.Path(__file__).resolve().parent.parent / "app/ui/theme.py")
    theme = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(theme)
    css = theme.STYLESHEET
    for sel in ("QAbstractItemView QLineEdit", "QAbstractItemView QDoubleSpinBox:focus", "QAbstractItemView QLineEdit:focus"):
        assert sel in css                                         # incl. :focus, which would otherwise win over the override
    assert "padding: 0px 4px; margin: 0px; min-height: 0px" in css


def test_columns_for_fits_width():
    from app.ui.layout_math import columns_for
    assert columns_for(1800, 250, 20, 4, (4, 2, 1)) == 4
    assert columns_for(1000, 250, 20, 4, (4, 2, 1)) == 2      # 3 would leave a lonely button -> 2
    assert columns_for(400, 250, 20, 4, (4, 2, 1)) == 1
    assert columns_for(100, 250) == 1
    assert columns_for(900, 205) == 4


# ---------- 7-day free trial ----------
class _MemStore:
    def __init__(self, text=""):
        self.text = text

    def read(self):
        return self.text

    def write(self, text):
        self.text = text


def test_trial_starts_by_itself_and_lasts_seven_days(tmp_path):
    from datetime import date, timedelta
    from app.services import licensing as L
    stores, d0 = [_MemStore(), _MemStore(), _MemStore()], date(2026, 11, 12)
    st = L.overall(tmp_path, d0, "PC-A", stores=stores)
    assert st["can_run"] and st["state"] == "trial" and st["days_left"] == 7 and "Free Trial" in st["label"]
    assert all(s.text for s in stores)                                    # saved in every place
    assert L.overall(tmp_path, d0 + timedelta(days=6), "PC-A", stores=stores)["days_left"] == 1
    st = L.overall(tmp_path, d0 + timedelta(days=7), "PC-A", stores=stores)
    assert not st["can_run"] and st["label"] == "Trial Expired" and "trial has ended" in st["reason"]
    assert not L.overall(tmp_path, d0 + timedelta(days=400), "PC-A", stores=stores)["can_run"]


def test_trial_cannot_be_reset_by_reinstall_or_date_change(tmp_path):
    from datetime import date, timedelta
    from app.services import licensing as L
    stores, d0 = [_MemStore(), _MemStore(), _MemStore()], date(2026, 11, 12)
    L.trial_status(tmp_path, d0, "PC-A", stores)
    L.trial_status(tmp_path, d0 + timedelta(days=5), "PC-A", stores)
    # re-install / data folder deleted: two of the three copies are gone -> same trial goes on, copies come back
    stores[0].text = stores[2].text = ""
    st = L.trial_status(tmp_path, d0 + timedelta(days=5), "PC-A", stores)
    assert st["days_left"] == 2 and st["start"] == d0 and stores[0].text == stores[1].text == stores[2].text
    # Windows date moved back: no extra days
    st = L.trial_status(tmp_path, d0 - timedelta(days=30), "PC-A", stores)
    assert not st["active"] and "date was moved back" in st["reason"]
    assert L.trial_status(tmp_path, d0 + timedelta(days=5), "PC-A", stores)["days_left"] == 2   # date corrected
    # a record edited by hand does not count; with no honest copy left the trial is over
    edited = stores[1].text.replace("2026-11-12", "2026-12-30")
    assert L.trial_status(tmp_path, d0 + timedelta(days=5), "PC-A", [_MemStore(edited), stores[0]])["days_left"] == 2
    assert not L.trial_status(tmp_path, d0 + timedelta(days=5), "PC-A", [_MemStore(edited)])["active"]
    # a data folder copied from another computer starts that computer's own trial
    assert L.trial_status(tmp_path, d0 + timedelta(days=20), "PC-B", [_MemStore(stores[0].text)])["days_left"] == 7


def test_key_activates_during_and_after_trial_and_data_is_untouched(tmp_path):
    from datetime import date, timedelta
    from app.services import licensing as L
    stores, d0 = [_MemStore(), _MemStore()], date(2026, 11, 12)
    (tmp_path / "business.db").write_bytes(b"shop data")
    L.overall(tmp_path, d0, "PC-A", stores=stores)
    late = d0 + timedelta(days=30)
    assert L.overall(tmp_path, late, "PC-A", stores=stores)["state"] == "expired"
    key, pub, _ = _issue("PC-A", None)
    assert L.activate(tmp_path, "wrong key", "PC-A", pub)[0] is False
    assert L.overall(tmp_path, late, "PC-A", pub, stores)["state"] == "expired"
    assert L.activate(tmp_path, key, "PC-A", pub)[0] is True
    st = L.overall(tmp_path, late, "PC-A", pub, stores)
    assert st["can_run"] and st["label"] == "Lifetime Activated"
    assert L.overall(tmp_path, late + timedelta(days=3000), "PC-A", pub, stores)["label"] == "Lifetime Activated"
    assert (tmp_path / "business.db").read_bytes() == b"shop data"
    # the file store really writes and reads back
    fs = L.FileStore(tmp_path / "sub" / "t.dat")
    L.trial_status(tmp_path, d0, "PC-X", [fs])
    assert L.trial_status(tmp_path, d0 + timedelta(days=3), "PC-X", [L.FileStore(tmp_path / "sub" / "t.dat")])["days_left"] == 4


# ---------- Purchase 2nd Hand Phone ----------
U1, U2, U3, U4 = "861234500000011", "861234500000029", "861234500000037", "861234500000045"


def _used(db, imei1=U1, imei2="", price=20000, sale=26000, model="Infinix Hot 40", seller="Kamran", **kw):
    from app.services import used_phones
    return used_phones.purchase(db, seller, model, imei1, price, cnic=kw.pop("cnic", "1510112345671"),
                                address="Sahara Center, Buner", phone="03001112223", model_no="X6836",
                                imei2=imei2, sale_price=sale, **kw)


def test_used_phone_with_one_imei_goes_into_stock_and_cash(shop):
    from app.services import used_phones
    db, sup, cust, _ = shop
    cash0, phones0 = reports.cash_in_hand(db), reports.dashboard(db)["phones_in_stock"]
    rid = _used(db)                                                       # only IMEI 1: must be accepted
    r = used_phones.detail(db, rid)
    assert r["no"] == "UPH-00001" and r["imei2"] is None and r["status"] == "In stock"
    assert r["cnic"] == "15101-1234567-1" and r["seller_name"] == "Kamran" and r["address"] and r["phone"]
    assert reports.dashboard(db)["phones_in_stock"] == phones0 + 1        # Phones in Stock goes up at once
    p = db.one("SELECT * FROM products WHERE id=?", (r["product_id"],))
    assert p["name"] == "Infinix Hot 40 X6836 (2nd Hand)" and p["track_serial"] == 1 and p["imei_mode"] == "single"
    assert p["avg_cost"] == 20000 and p["sale_price"] == 26000 and p["category"] == "Mobile Phone"
    assert stock_qty(db.conn, p["id"]) == 1
    assert reports.cash_in_hand(db) == cash0 - 20000                      # paid in cash, nothing left owing
    assert reports.all_balances(db, "supplier")["total"] == 0
    assert any(x["name"] == p["name"] for x in masters.search_products(db, "infinix"))   # in the normal product list
    look = reports.imei_lookup(db, U1)[0]
    assert look["status"] == "in_stock" and look["supplier"] == "Kamran (2nd hand)"


def test_used_phone_with_two_imeis_and_duplicates_are_refused(shop):
    from app.services import used_phones
    db = shop[0]
    rid = _used(db, U1, U2)
    r = used_phones.detail(db, rid)
    assert (r["imei1"], r["imei2"]) == (U1, U2)
    assert db.one("SELECT imei_mode FROM products WHERE id=?", (r["product_id"],))["imei_mode"] == "double"
    for a, b in ((U1, ""), (U3, U2), (U2, ""), (U3, U3)):                 # same phone again / same number twice
        with pytest.raises(BusinessError):
            _used(db, a, b)
    for bad in dict(imei1=""), dict(imei1="12ab"), dict(price=0), dict(seller=" "), dict(model=""), dict(cnic="123"):
        with pytest.raises(BusinessError):
            _used(db, **{"imei1": U4, **bad})
    assert db.scalar("SELECT COUNT(*) FROM used_phones") == 1 and db.scalar("SELECT COUNT(*) FROM serials") == 1
    assert db.scalar("SELECT COUNT(*) FROM purchases") == 1               # a refused purchase leaves nothing behind
    _used(db, U4, cnic="")                                                # CNIC may be left empty


def test_used_phone_is_sold_on_the_normal_invoice_with_its_own_cost(shop):
    from app.services import used_phones
    db, sup, cust, _ = shop
    a = used_phones.detail(db, _used(db, U1, price=20000, sale=26000))
    b = used_phones.detail(db, _used(db, U2, price=31000, sale=36000))    # same model, other cost: own stock line
    c = used_phones.detail(db, _used(db, U3, price=20000, sale=26000))    # same cost and price: shares A's line
    assert b["product_id"] != a["product_id"] and c["product_id"] == a["product_id"]
    assert b["product_name"].endswith("#2")
    assert db.one("SELECT avg_cost FROM products WHERE id=?", (b["product_id"],))["avg_cost"] == 31000
    assert stock_qty(db.conn, a["product_id"]) == 2
    inv = trading.create_invoice(db, cust, [{"product_id": b["product_id"], "qty": 1, "price": 35000, "serial": U2}],
                                 paid=35000)
    assert trading.invoice_profit(db, inv) == 4000                        # 35,000 - its own 31,000
    sold = used_phones.detail(db, b["id"])
    assert sold["status"] == "Sold" and sold["sold_price"] == 35000 and sold["profit"] == 4000
    assert sold["invoice_no"] == "INV-00001"
    assert stock_qty(db.conn, b["product_id"]) == 0 and reports.dashboard(db)["phones_in_stock"] == 2
    # the empty line is used again for the next phone of that model, with the new cost and sale price
    d = used_phones.detail(db, _used(db, U4, price=18000, sale=23000))
    assert d["product_id"] == b["product_id"]
    p = db.one("SELECT avg_cost, sale_price FROM products WHERE id=?", (d["product_id"],))
    assert (p["avg_cost"], p["sale_price"]) == (18000, 23000)
    # a phone that was sold can be bought back later; it is in stock once, never twice
    again = used_phones.detail(db, _used(db, U2, price=25000, sale=30000, seller="Ali"))
    assert again["status"] == "In stock" and db.scalar("SELECT COUNT(*) FROM serials WHERE serial=?", (U2,)) == 1
    with pytest.raises(BusinessError):
        _used(db, U2)
    hist = used_phones.history(db)
    assert [h["no"] for h in hist][0] == "UPH-00005" and len(hist) == 5
    assert [h["imei1"] for h in used_phones.history(db, "Ali")] == [U2]
    assert len(used_phones.history(db, U1[-6:])) == 1
    for key in ("seller_name", "model", "model_no", "imei1", "imei2", "price", "date", "sale_price"):
        assert key in hist[0]


# ---------- Cash Loan ----------
def test_cash_loan_repayments_and_outstanding_without_double_counting(shop):
    from app.reports import builders as B
    from app.services import loans
    db, sup, cust, prod = shop
    trading.create_purchase(db, sup, [{"product_id": prod, "qty": 5, "price": 40000}], paid=200000)
    trading.create_invoice(db, cust, [{"product_id": prod, "qty": 1, "price": 50000}], paid=10000)   # Ali owes 40,000
    cash0, equity0 = reports.cash_in_hand(db), reports.balance_sheet(db)["equity"]
    pid = loans.give_loan(db, "Rashid Khan", 20000, cnic="15101-7654321-9", phone="03451234567",
                          address="Buner", note="personal")
    assert loans.balance(db.conn, pid) == 20000 and reports.cash_in_hand(db) == cash0 - 20000
    assert reports.balance_sheet(db)["equity"] == equity0                 # lent cash is still ours
    o = reports.outstanding(db)
    assert (o["customer_total"], o["loan_total"], o["total"]) == (40000, 20000, 60000)
    assert reports.all_balances(db, "customer")["total"] == 40000         # the customer's account is untouched
    assert loans.receive_repayment(db, pid, 5000) == 15000                # the example from the request
    assert loans.receive_repayment(db, pid, 5000) == 10000
    assert reports.cash_in_hand(db) == cash0 - 10000
    with pytest.raises(BusinessError):
        loans.receive_repayment(db, pid, 10000.5)                         # more than what is left
    with pytest.raises(BusinessError):
        loans.receive_repayment(db, pid, 0)
    # another loan to the same person (same CNIC) lands in the same account
    assert loans.give_loan(db, "Rashid Khan", 7000, cnic="1510176543219") == pid
    assert loans.balance(db.conn, pid) == 17000
    other = loans.give_loan(db, "Naveed", 3000)
    assert other != pid and loans.give_loan(db, "naveed", 1000) == other
    rows = {r["name"]: r for r in loans.people(db)}
    assert (rows["Rashid Khan"]["given"], rows["Rashid Khan"]["returned"], rows["Rashid Khan"]["balance"]) == (27000, 10000, 17000)
    assert [h["balance"] for h in loans.history(db, pid)] == [20000, 15000, 10000, 17000]
    assert [h["kind"] for h in loans.history(db, pid)] == ["loan", "repayment", "repayment", "loan"]
    rep = B.outstanding_report(db)
    kinds = [r[1] for r in rep["rows"] if r[1]]
    assert kinds == ["Customer", "Cash Loan", "Cash Loan"] and rep["title"] == "Outstanding"
    assert ("Total to receive", "61,000.00") in rep["summary"]
    assert ("Customer outstanding", "40,000.00") in rep["summary"] and ("Cash loan outstanding", "21,000.00") in rep["summary"]
    assert reports.dashboard(db)["outstanding"] == 61000 and reports.dashboard(db)["receivable"] == 40000
    # full repayment brings the person to zero and out of the Outstanding list
    assert loans.receive_repayment(db, pid, 17000) == 0
    with pytest.raises(BusinessError):
        loans.receive_repayment(db, pid, 1)
    assert [r["name"].lower() for r in loans.people(db, only_open=True)] == ["naveed"]
    assert reports.outstanding(db)["total"] == 44000 and reports.balance_sheet(db)["cash_loans"] == 4000
    assert reports.balance_sheet(db)["equity"] == equity0
    cb = B.cash_book_report(db, "2000-01-01", "2100-01-01")
    assert any("Cash loan given: Rashid Khan" in r[1] for r in cb["rows"])
    assert any("Cash loan repaid: Rashid Khan" in r[1] for r in cb["rows"])
    for bad in dict(name=""), dict(amount=0), dict(amount=-5), dict(cnic="12"):
        with pytest.raises(BusinessError):
            loans.give_loan(db, **{"name": "X", "amount": 100, **bad})


def test_reset_handles_used_phones_and_loans(shop):
    from app.services import loans, reset, used_phones
    db = shop[0]
    _used(db)
    pid = loans.give_loan(db, "Rashid", 9000)
    reset.reset_data(db, PW, "clear balances test", ["balances"])
    assert loans.balance(db.conn, pid) == 0 and reports.outstanding(db)["total"] == 0
    assert loans.history(db, pid)[-1]["kind"] == "adjustment"
    reset.reset_data(db, PW, "erase everything test", ["products"])
    assert used_phones.history(db) == [] and loans.people(db) == []
    assert db.scalar("SELECT COUNT(*) FROM products") == 0


def test_new_screens_names_and_colours():
    from app.reports import charts, home_icons
    from app.services import permissions
    from app.ui.menu_spec import HOME_BUTTONS, IMPLEMENTED, MENUS
    labels = [l for l, _ in HOME_BUTTONS] + [l for _, items in MENUS for l, _ in items]
    assert "Outstanding" in labels and not any("baqaya" in l.lower() for l in labels)
    menus = dict(MENUS)
    assert ("Cash Loan", "cash_loan") in menus["Utilities"]
    assert ("Purchase 2nd Hand Phone", "used_phone") in menus["Sale/Purchase"]
    assert {"used_phone", "used_phone_history", "cash_loan"} <= IMPLEMENTED
    for key in ("used_phone", "cash_loan"):                               # purchase prices and loans: owner only
        assert permissions.can_open("owner", key) and not permissions.can_open("staff", key)
    modules = _import_with_qt_stub("app.ui.modules")
    assert {"used_phone", "used_phone_history", "cash_loan"} <= set(modules.MODULES)
    import importlib.util, pathlib
    spec = importlib.util.spec_from_file_location("theme", pathlib.Path(__file__).resolve().parent.parent / "app/ui/theme.py")
    theme = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(theme)
    assert set(theme.ACCENTS) == set(home_icons.PALETTE) == {"navy", "red", "green", "gold", "cyan", "purple", "orange", "teal"}
    for name, hex_color in theme.ACCENTS.items():
        assert theme.rgb(hex_color) == home_icons.PALETTE[name]           # screens and icons use the same colours
    assert theme.blend("#000000", "#FFFFFF", 0.5) == "#808080"
    for key in home_icons.HOME_ICONS:
        assert home_icons.home_icon_png(key, 52, home_icons.PALETTE["red"])[:4] == b"\x89PNG"
    for key in home_icons.BADGES:
        assert home_icons.badge_png(key, 30)[:4] == b"\x89PNG" and home_icons.badge_png(key, 30, "teal", True)
    assert charts.to_png(charts.bar_chart([("a", 5), ("b", 9)], "t", size=(300, 180), color=charts.PURPLE))


# ---------- phones: type, RAM, storage; Phones in Stock ----------
P1, P2, P3, P4 = "353000000000013", "353000000000021", "353000000000039", "353000000000047"


def test_smartphone_needs_ram_and_storage_keypad_does_not(shop):
    from app.services import phones
    db, sup, cust, _ = shop
    with pytest.raises(BusinessError):                                   # a new smartphone without RAM / storage
        masters.add_product(db, "Infinix Note 40 Pro", 29000, category="Mobile Phone", mobile_type="smartphone")
    with pytest.raises(BusinessError):
        masters.add_product(db, "Infinix Note 40 Pro", 29000, category="Mobile Phone", mobile_type="smartphone",
                            ram_gb="eight", storage_gb=256)
    smart = masters.add_product(db, "Note 40 Pro", 29000, category="Mobile Phone", mobile_type="smartphone",
                                ram_gb=8, storage_gb=256, brand="Infinix", condition="new")
    keypad = masters.add_product(db, "Nokia 105", 3500, category="Mobile Phone", mobile_type="keypad",
                                 ram_gb=4, storage_gb=64, brand="Nokia")          # sizes are ignored for a keypad phone
    old = masters.add_product(db, "Old Record Phone", 9000, category="Mobile Phone")   # as before this feature
    s, k, o = (db.one("SELECT * FROM products WHERE id=?", (x,)) for x in (smart, keypad, old))
    assert (s["mobile_type"], s["ram_gb"], s["storage_gb"], s["brand"]) == ("smartphone", 8, 256, "Infinix")
    assert (k["mobile_type"], k["ram_gb"], k["storage_gb"]) == ("keypad", None, None)
    assert (o["mobile_type"], o["ram_gb"], o["storage_gb"]) == (None, None, None)
    assert phones.spec(s) == "8 GB / 256 GB" and phones.spec(k) == "Keypad" and phones.spec(o) == ""
    assert phones.gb(4) == "4 GB" and phones.gb(None) == "-"
    masters.update_product(db, smart, ram_gb=12)
    assert db.one("SELECT ram_gb, storage_gb FROM products WHERE id=?", (smart,)) == {"ram_gb": 12, "storage_gb": 256}
    with pytest.raises(BusinessError):
        masters.update_product(db, smart, storage_gb=0)                   # a smartphone cannot lose its storage
    masters.update_product(db, old, sale_price=9500)                      # old records stay editable as they are
    other = masters.add_product(db, "Charger", 500, category="Accessories", mobile_type="smartphone")
    assert db.one("SELECT mobile_type FROM products WHERE id=?", (other,))["mobile_type"] is None


def test_phones_in_stock_list_filters_and_sold_phones_disappear(shop):
    from app.services import phones
    db, sup, cust, _ = shop
    smart = masters.add_product(db, "Note 40 Pro", 29000, category="Mobile Phone", mobile_type="smartphone",
                                ram_gb=8, storage_gb=256, brand="Infinix")
    keypad = masters.add_product(db, "Nokia 105", 3500, category="Mobile Phone", mobile_type="keypad", brand="Nokia")
    old = masters.add_product(db, "Old Record Phone", 9000, category="Mobile Phone")
    trading.create_purchase(db, sup, [{"product_id": smart, "qty": 2, "price": 25000, "serials": [P1, P2]},
                                      {"product_id": keypad, "qty": 1, "price": 3000, "serials": [P3]},
                                      {"product_id": old, "qty": 1, "price": 8000, "serials": [P4]}], paid=61000)
    _used(db, U1, price=20000, sale=26000, mobile_type="smartphone", ram_gb=4, storage_gb=128)
    rows = phones.in_stock(db)
    assert len(rows) == 5 == reports.dashboard(db)["phones_in_stock"]
    by = {r["imei1"]: r for r in rows}
    assert (by[P1]["brand"], by[P1]["ram_gb"], by[P1]["storage_gb"], by[P1]["condition"]) == ("Infinix", 8, 256, "new")
    assert (by[P1]["purchase_price"], by[P1]["sale_price"], by[P1]["status"]) == (25000, 29000, "Available")
    assert by[P3]["mobile_type"] == "keypad" and by[P3]["ram_gb"] is None
    assert by[P4]["mobile_type"] is None and by[P4]["condition"] == "new"       # an old record still works
    assert (by[U1]["condition"], by[U1]["purchase_price"], by[U1]["sale_price"]) == ("used", 20000, 26000)
    assert by[U1]["brand"] == "Infinix" and "4/128GB" in by[U1]["name"]
    assert {r["imei1"] for r in phones.in_stock(db, condition="used")} == {U1}
    assert {r["imei1"] for r in phones.in_stock(db, ram=8)} == {P1, P2}
    assert {r["imei1"] for r in phones.in_stock(db, storage=128)} == {U1}
    assert {r["imei1"] for r in phones.in_stock(db, mobile_type="keypad")} == {P3}
    assert {r["imei1"] for r in phones.in_stock(db, "nokia")} == {P3}
    assert [r["imei1"] for r in phones.in_stock(db, P2[-7:])] == [P2]            # search by IMEI
    assert [r["purchase_price"] for r in phones.in_stock(db, sort="purchase")] == [3000, 8000, 20000, 25000, 25000]
    assert phones.in_stock(db, sort="sale", descending=True)[0]["sale_price"] == 29000
    assert phones.filter_values(db) == {"ram": [4, 8], "storage": [128, 256]}
    trading.create_invoice(db, cust, [{"product_id": smart, "qty": 1, "price": 29000, "serial": P1}], paid=29000)
    assert P1 not in {r["imei1"] for r in phones.in_stock(db)} and len(phones.in_stock(db)) == 4
    sold = db.one("SELECT p.ram_gb, p.storage_gb FROM serials s JOIN products p ON p.id=s.product_id WHERE s.serial=?", (P1,))
    assert sold == {"ram_gb": 8, "storage_gb": 256}                              # kept with the IMEI after the sale
    pd = reports.purchase_detail(db, 1)
    assert "[8 GB / 256 GB]" in pd["items"][0]["product_name"] and "[Keypad]" in pd["items"][1]["product_name"]
    with pytest.raises(BusinessError):
        _used(db, U2, mobile_type="smartphone")                                  # used smartphone: sizes required
    _used(db, U2, mobile_type="keypad", model="Nokia 106")                       # keypad: not required


def test_database_update_keeps_a_backup_and_old_products(tmp_path):
    from app.db.schema import SCHEMA_VERSION
    db = Database(tmp_path, PW, create=True)
    with db.transaction() as c:
        c.execute("INSERT INTO products(name, category, track_serial) VALUES('Old phone', 'Mobile Phone', 1)")
        c.execute("PRAGMA user_version = 3")
    db.close()
    db = Database(tmp_path, PW)
    assert db.scalar("PRAGMA user_version") == SCHEMA_VERSION
    assert (tmp_path / "backups" / f"before-update-v3-to-v{SCHEMA_VERSION}.bmdb").exists()
    p = db.one("SELECT * FROM products WHERE name='Old phone'")
    assert p["id"] == 1 and p["ram_gb"] is None and p["mobile_type"] is None
    db.close()


# ---------- Outstanding SMS template ----------
def test_sms_template_placeholder_versions_and_business_details(shop):
    from app.services import sms_template as T
    db = shop[0]
    assert T.render("آپ کے لیجر کے مطابق (****) روپے", 5000) == "آپ کے لیجر کے مطابق 5,000 روپے"
    assert T.render("Rs **** due, again ****.", 12500.4) == "Rs 12,500 due, again 12,500."
    assert T.render("( **** ) / ****", 7) == "7 / 7"
    for bad in ("", "No stars here", "three ***", "five *****", "eight ********"):
        with pytest.raises(BusinessError):
            T.check(bad)
    assert T.count_slots("a **** b (****) c ***** d") == 2
    cur = T.current(db)
    assert cur["version"] == 0 and "(****)" in cur["text"] and "محترم صارف" in cur["text"]
    v1 = T.save(db, "Pay **** please", base_version=0)
    assert v1["version"] == 1 and T.current(db)["text"] == "Pay **** please" and v1["updated_by"] == "Windows"
    with pytest.raises(T.TemplateConflict) as exc:                       # an older copy cannot overwrite a newer one
        T.save(db, "Old phone copy ****", base_version=0, by="Android")
    assert exc.value.current["version"] == 1 and T.current(db)["text"] == "Pay **** please"
    with pytest.raises(BusinessError):
        T.save(db, "forgot the stars", base_version=1)
    v2 = T.save(db, "Newer **** text", base_version=1, by="Android (Zia)")
    assert v2["version"] == 2 and T.current(db)["updated_by"] == "Android (Zia)"
    # business details belong to this installation and feed the default message
    with db.transaction() as c:
        c.execute("UPDATE company SET name='Khan Mobiles', phone='0300-1112223' WHERE id=1")
    assert T.business(db)["easypaisa"] == "" and T.business(db)["business_name"] == "Khan Mobiles"
    assert T.business(db)["easypaisa"] == "" and "Easypaisa" not in T.default_text(db)
    T.save_business(db, business_name="Khan Mobiles", contact="0300-1112223", account_name="Khan",
                    easypaisa="03001112223", jazzcash="03004445556", other="Bank: HBL 1234")
    d = T.default_text(db)
    assert d.startswith("Khan Mobiles\n") and "03001112223" in d and "JazzCash" in d and "Bank: HBL 1234" in d
    assert "Burhan" not in d and "03139271732" not in d and "(****)" in d
    assert T.restore_default(db, base_version=2)["text"] == d
    with pytest.raises(BusinessError):
        T.save_business(db, business_name=" ")


def test_default_message_of_burhan_nexus_is_the_requested_one(tmp_path):
    from app.services import sms_template as T
    db = auth.register(tmp_path, "Burhan Nexus", "Sahara Center, Buner", "03475093446", "a@b.c", None, "admin", PW, PW)
    text = T.current(db)["text"]
    for part in ("Burhan Nexus", "📞 0347-5093446", "محترم صارف،", "(****) روپے کی رقم تاحال واجب الادا ہے",
                 "Easypaisa ادائیگی کی تفصیل:", "نام: Ziaullah", "نمبر: 03139271732", "تہہ دل سے شکریہ۔"):
        assert part in text
    assert "12,500 روپے" in T.render(text, 12500) and "*" not in T.render(text, 12500)
    db.close()


# ---------- Android Companion: pairing, encryption, data ----------
class _Phone:
    """What the Android app does, written with the same primitives (see android/.../Crypto.java)."""

    def __init__(self, device_id="phone-0001-abcdef"):
        self.id, self.key = device_id, None

    def pair_body(self, hello, code):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from app.services import companion as C
        priv = ec.generate_private_key(ec.SECP256R1())
        shared = priv.exchange(ec.ECDH(), serialization.load_der_public_key(C._unb64(hello["pub"])))
        self.key = C.session_key(shared, code, self.id)
        pub = priv.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
        return {"device_id": self.id, "name": "Test Phone", "pub": C._b64(pub), "proof": C.proof(self.key, "pair|" + self.id)}

    def ask(self, db, op, **args):
        from app.services import companion as C
        out = C.unseal(self.key, C.api(db, C.seal(self.key, self.id, {"op": op, "args": args})))
        return out


def _paired(db):
    from app.services import companion as C
    pairing, phone = C.Pairing(), _Phone()
    code = pairing.start()
    ans = C.pair(db, pairing, phone.pair_body(C.hello(db), code))
    assert ans["ok"] and ans["proof"] == C.proof(phone.key, "ok|" + ans["server_id"])
    return phone


def test_companion_pairing_needs_the_code_and_unknown_phones_get_nothing(shop):
    from app.services import companion as C
    db = shop[0]
    pairing, phone = C.Pairing(), _Phone()
    with pytest.raises(C.ApiError) as e:                                 # pairing not opened on the PC
        C.pair(db, pairing, phone.pair_body(C.hello(db), "123456"))
    assert e.value.code == "no_code"
    code = pairing.start()
    wrong = "000000" if code != "000000" else "111111"
    with pytest.raises(C.ApiError) as e:
        C.pair(db, pairing, phone.pair_body(C.hello(db), wrong))
    assert e.value.code == "wrong_code" and C.devices(db) == []
    stranger = _Phone("stranger-device-01")
    stranger.key = os.urandom(32)
    with pytest.raises(C.ApiError) as e:                                 # not paired: nothing is readable
        stranger.ask(db, "sync")
    assert e.value.status == 401
    C.pair(db, pairing, phone.pair_body(C.hello(db), code))
    assert [d["name"] for d in C.devices(db)] == ["Test Phone"] and not pairing.active()   # one phone per code
    assert phone.ask(db, "status")["ok"]
    thief = _Phone(phone.id)                                             # right id, wrong key
    thief.key = os.urandom(32)
    with pytest.raises(C.ApiError):
        thief.ask(db, "sync")
    for _ in range(C.CODE_TRIES):                                        # five wrong tries close the code
        code2 = pairing.code or pairing.start()
        with pytest.raises(C.ApiError):
            C.pair(db, pairing, _Phone("another-device-02").pair_body(C.hello(db), "999999" if code2 != "999999" else "888888"))
    assert not pairing.active()
    C.remove_device(db, phone.id)
    with pytest.raises(C.ApiError):
        phone.ask(db, "status")
    assert "priv" not in C.hello(db) and set(C.hello(db)) == {"app", "api", "server_id", "shop", "pub", "port"}


def test_companion_sync_shows_real_outstanding_and_follows_changes(shop):
    from app.services import companion as C, installments, loans
    db, sup, cust, prod = shop
    trading.create_purchase(db, sup, [{"product_id": prod, "qty": 9, "price": 100}], paid=900)
    phone = _paired(db)
    data = phone.ask(db, "sync")["data"]
    assert data["customers"] == [] and data["summary"]["total_outstanding"] == 0
    bilal = masters.add_party(db, "customer", "Bilal", phone="0347-5093446")           # new customer on the PC
    trading.create_invoice(db, bilal, [{"product_id": prod, "qty": 1, "price": 12500}], paid=2500)
    paidup = masters.add_party(db, "customer", "Paid Up", phone="0300-0000000")
    trading.create_invoice(db, paidup, [{"product_id": prod, "qty": 1, "price": 900}], paid=900)
    lid = loans.give_loan(db, "Rashid", 6000, phone="0345-1234567")
    data = phone.ask(db, "sync")["data"]
    rows = {r["id"]: r for r in data["customers"]}
    assert set(rows) == {f"C-{bilal}", f"L-{lid}"}                                     # only real positive balances
    b = rows[f"C-{bilal}"]
    assert (b["name"], b["phone"], b["total_purchase"], b["total_paid"], b["balance"]) == ("Bilal", "0347-5093446", 12500, 2500, 10000)
    assert b["type"] == "customer" and b["last_payment"] and b["ledger"][-1]["balance"] == 10000
    assert rows[f"L-{lid}"]["type"] == "loan" and rows[f"L-{lid}"]["balance"] == 6000
    assert data["summary"] == {"total_outstanding": 16000, "customers": 2, "today_recoveries": 0, "overdue_count": 0,
                               "overdue_amount": 0, "currency": "PKR"}
    assert [r["balance"] for r in data["customers"]] == [10000, 6000]                  # highest first
    payments.receive_from_customer(db, bilal, 4000)                                    # payment recorded on the PC
    loans.receive_repayment(db, lid, 1000)
    data = phone.ask(db, "sync")["data"]
    rows = {r["id"]: r for r in data["customers"]}
    assert rows[f"C-{bilal}"]["balance"] == 6000 and rows[f"C-{bilal}"]["total_paid"] == 6500
    assert data["summary"]["today_recoveries"] == 5000 and data["summary"]["total_outstanding"] == 11000
    assert len({l["id"] for l in rows[f"C-{bilal}"]["ledger"]}) == len(rows[f"C-{bilal}"]["ledger"])   # unique ids
    assert [p["credit"] for p in phone.ask(db, "payments", id=f"C-{bilal}")["data"]] == [2500, 4000]
    assert phone.ask(db, "ledger", id=f"L-{lid}")["data"][-1]["balance"] == 5000
    assert phone.ask(db, "summary")["data"]["customers"] == 2 and phone.ask(db, "transactions")["data"]
    assert "ledger" not in phone.ask(db, "customers")["data"][0]
    # overdue: a late qist, or nothing paid for more than 30 days
    from datetime import date, timedelta
    late = C.outstanding_list(db, False, today=date.today() + timedelta(days=45))
    assert all(r["overdue"] and "No payment for" in r["overdue_reason"] for r in late)
    assert C.summary(db, late)["overdue_count"] == 2
    payments.receive_from_customer(db, bilal, 6000)                                    # fully paid: leaves the list
    assert {r["id"] for r in phone.ask(db, "sync")["data"]["customers"]} == {f"L-{lid}"}
    assert phone.ask(db, "ledger", id=f"C-{bilal}")["ok"] is False
    assert phone.ask(db, "no_such_op")["error"] == "unknown_op"


def test_companion_template_is_shared_and_newest_wins(shop):
    from app.services import sms_template as T
    db = shop[0]
    phone = _paired(db)
    t0 = phone.ask(db, "template_get")["data"]
    assert t0["version"] == 0 and "****" in t0["text"]
    T.save(db, "From Windows ****", base_version=0)                       # edited on the PC
    assert phone.ask(db, "sync")["data"]["template"]["text"] == "From Windows ****"
    stale = phone.ask(db, "template_save", text="Stale phone copy ****", base_version=0)
    assert stale["ok"] is False and stale["error"] == "conflict" and stale["data"]["text"] == "From Windows ****"
    assert T.current(db)["text"] == "From Windows ****"
    bad = phone.ask(db, "template_save", text="no stars", base_version=1)
    assert bad["ok"] is False and bad["error"] == "invalid" and "****" in bad["message"]
    ok = phone.ask(db, "template_save", text="From Android ****", base_version=1)
    assert ok["ok"] and ok["data"]["version"] == 2 and ok["data"]["updated_by"].startswith("Android")
    assert T.current(db)["text"] == "From Android ****"                   # ... and Windows shows it
    biz = phone.ask(db, "business_save", business_name="Khan Mobiles", easypaisa="03001112223")["data"]
    assert biz["business_name"] == "Khan Mobiles" and T.business(db)["easypaisa"] == "03001112223"
    assert phone.ask(db, "business_get")["data"] == T.business(db)
    restored = phone.ask(db, "template_save", restore_default=True, base_version=2)["data"]
    assert restored["version"] == 3 and restored["text"].startswith("Khan Mobiles")


def test_companion_server_over_the_network_with_discovery(shop):
    """Real sockets on this machine: UDP discovery, /hello, /pair and an encrypted /api call."""
    import json, queue, socket, threading, urllib.error, urllib.request
    from app.services import companion as C
    from app.services.companion_server import CompanionServer
    db = shop[0]
    jobs = queue.Queue()

    def run(job):                                                         # like the Qt bridge: the main thread works
        if threading.current_thread() is threading.main_thread():
            return job()
        box = {"done": threading.Event()}
        jobs.put((job, box))
        assert box["done"].wait(10)
        if "error" in box:
            raise box["error"]
        return box["result"]

    def on_main(fn):                                                      # do `fn` in a thread, serve jobs meanwhile
        out = {}
        t = threading.Thread(target=lambda: out.update(v=fn()))
        t.start()
        while t.is_alive():
            try:
                job, box = jobs.get(timeout=0.02)
            except queue.Empty:
                continue
            try:
                box["result"] = job()
            except BaseException as exc:
                box["error"] = exc
            box["done"].set()
        return out["v"]

    pairing = C.Pairing()
    srv = CompanionServer(run, lambda: db, pairing, http_port=0, discovery_port=0, host="127.0.0.1")
    assert srv.start() and srv.running()
    base = f"http://127.0.0.1:{srv.http_port}"

    def http(path, body=None):
        req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    try:
        u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)             # "is a Business Manager here?"
        u.settimeout(5)
        u.sendto(C.DISCOVER_ASK, ("127.0.0.1", srv.discovery_port))
        found = json.loads(u.recvfrom(1024)[0])
        u.close()
        assert found["app"] == "BNBC" and found["port"] == srv.http_port and "pub" not in found
        status, hello = on_main(lambda: http("/hello"))
        assert status == 200 and hello["server_id"] == found["server_id"]
        phone = _Phone()
        code = pairing.start()
        status, ans = on_main(lambda: http("/pair", phone.pair_body(hello, code)))
        assert status == 200 and ans["ok"]
        status, env = on_main(lambda: http("/api", C.seal(phone.key, phone.id, {"op": "sync", "args": {}})))
        assert status == 200 and set(env) == {"d", "n", "c"}             # nothing readable on the wire
        assert "customers" not in json.dumps(env)
        assert C.unseal(phone.key, env)["data"]["summary"]["currency"] == "PKR"
        status, err = on_main(lambda: http("/api", C.seal(os.urandom(32), phone.id, {"op": "sync"})))
        assert status == 401 and err["error"] == "not_paired"
        assert on_main(lambda: http("/api", {"d": "nobody", "n": "", "c": ""}))[0] == 401
        assert on_main(lambda: http("/nothing", {}))[0] == 404
    finally:
        srv.stop()


def test_android_crypto_and_template_match_the_pc(shop, tmp_path):
    """Compiles the Android app's Crypto.java / Template.java and runs them against the PC code."""
    import base64, shutil, subprocess
    if not shutil.which("javac"):
        pytest.skip("no Java compiler here")
    from app.services import companion as C, sms_template as T
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = os.path.join(root, "android", "app", "src", "main", "java", "com", "burhannexus", "companion")
    subprocess.run(["javac", "-d", str(tmp_path), os.path.join(src, "Crypto.java"), os.path.join(src, "Template.java"),
                    os.path.join(root, "tests", "java", "Interop.java")], check=True, capture_output=True)

    def java(*args):
        return subprocess.run(["java", "-cp", str(tmp_path), "Interop", *args], check=True, capture_output=True,
                              text=True).stdout.strip().split("\n")

    db = shop[0]
    pairing, device = C.Pairing(), "android-device-0001"
    code = pairing.start()
    pub, proof, key, nonce, cipher = java("pair", C.hello(db)["pub"], code, device, '{"op":"status","args":{}}')
    ans = C.pair(db, pairing, {"device_id": device, "name": "Java", "pub": pub, "proof": proof})
    assert ans["ok"] and java("proof", key, "ok|" + ans["server_id"]) == [ans["proof"]]
    env = C.api(db, {"d": device, "n": nonce, "c": cipher})               # sealed by Java, opened by the PC
    opened = java("open", key, device, env["n"], env["c"])[0]            # sealed by the PC, opened by Java
    assert '"ok":true' in opened and '"shop"' in opened
    for text, amount in (("آپ کے لیجر کے مطابق (****) روپے", 5000), ("a **** b ( **** ) c *****", 12500.4),
                         (T.default_text(db), 987654)):
        b64 = base64.b64encode(text.encode()).decode()
        assert base64.b64decode(java("render", str(amount), b64)[0]).decode() == T.render(text, amount)
    assert java("render", "5", base64.b64encode("no stars ***".encode()).decode()) == ["<null>"]


def test_new_update_screens_are_wired():
    from app.services import permissions
    from app.ui.menu_spec import IMPLEMENTED, MENUS
    menus = dict(MENUS)
    assert ("Mobile App (Android)", "mobile_app") in menus["Utilities"]
    assert ("Outstanding SMS Template Settings", "sms_template") in menus["Utilities"]
    assert ("Phones in Stock", "phone_stock") in menus["Sale/Purchase"]
    assert {"phone_stock", "mobile_app", "sms_template"} <= IMPLEMENTED
    modules = _import_with_qt_stub("app.ui.modules")
    assert {"phone_stock", "mobile_app", "sms_template"} <= set(modules.MODULES)
    assert permissions.can_open("staff", "phone_stock")                   # staff may look up phones (no cost shown)
    for key in ("mobile_app", "sms_template"):
        assert permissions.can_open("owner", key) and not permissions.can_open("staff", key)


from app.services import phones as PH  # noqa: E402  (a fixture is also called "phones")


# ---------- purchase rate is editable; history keeps its own prices ----------
def test_purchase_rate_can_be_edited_without_changing_history(shop):
    db, sup, cust, _ = shop
    cover = masters.add_product(db, "Back Cover", sale_price=500, purchase_price=200, opening_stock=0,
                                category="Accessories")
    pur = trading.create_purchase(db, sup, [{"product_id": cover, "qty": 10, "price": 200}], paid=2000)
    inv = trading.create_invoice(db, cust, [{"product_id": cover, "qty": 2, "price": 500}], paid=1000)
    assert trading.invoice_profit(db, inv) == 600
    pl_before = reports.profit_loss(db, "2000-01-01", "2100-01-01")
    masters.update_product(db, cover, purchase_price=260)                   # the rate is corrected afterwards
    p = db.one("SELECT avg_cost, last_purchase_price FROM products WHERE id=?", (cover,))
    assert (p["avg_cost"], p["last_purchase_price"]) == (260, 260)
    # saved documents and their profit are unchanged
    assert trading.invoice_profit(db, inv) == 600
    assert db.one("SELECT unit_cost FROM invoice_items WHERE invoice_id=?", (inv,))["unit_cost"] == 200
    assert db.one("SELECT price FROM purchase_items WHERE purchase_id=?", (pur,))["price"] == 200
    assert reports.purchase_detail(db, pur)["purchase"]["total"] == 2000
    assert reports.profit_loss(db, "2000-01-01", "2100-01-01") == pl_before
    # from now on the new rate is used: stock value, the next sale's profit, the next purchase's suggestion
    row = [r for r in reports.stock_position(db)["rows"] if r["id"] == cover][0]
    assert row["qty"] == 8 and row["value"] == 8 * 260
    inv2 = trading.create_invoice(db, cust, [{"product_id": cover, "qty": 1, "price": 500}], paid=500)
    assert trading.invoice_profit(db, inv2) == 240
    for bad in (-1, "abc"):
        with pytest.raises(BusinessError):
            masters.update_product(db, cover, purchase_price=bad)
    assert db.one("SELECT avg_cost FROM products WHERE id=?", (cover,))["avg_cost"] == 260
    masters.update_product(db, cover, purchase_price=260, sale_price=550)   # same rate + other change is fine
    assert db.scalar("SELECT COUNT(*) FROM audit_log WHERE action='Product edited' AND detail LIKE '%purchase_price=260%'") >= 1


# ---------- mobile phones never appear in Low Stock ----------
def test_low_stock_never_lists_mobile_phones(shop):
    from app.reports import builders as B
    db, sup, cust, _ = shop
    phone = masters.add_product(db, "Tecno Spark 20", 30000, category="Mobile Phone", low_stock_level=5,
                                mobile_type="smartphone", ram_gb=8, storage_gb=128)
    keypad = masters.add_product(db, "Nokia 105", 3500, category="Mobile Phone", low_stock_level=3, mobile_type="keypad")
    charger = masters.add_product(db, "Charger", 800, category="Accessories", low_stock_level=5)
    cable = masters.add_product(db, "Cable", 300, category="Accessories", low_stock_level=0)
    plenty = masters.add_product(db, "Glass", 200, category="Accessories", low_stock_level=2)
    trading.create_purchase(db, sup, [{"product_id": phone, "qty": 1, "price": 25000, "serials": [P1]},
                                      {"product_id": charger, "qty": 3, "price": 400},
                                      {"product_id": plenty, "qty": 9, "price": 50}], paid=26650)
    low = {r["name"] for r in reports.stock_position(db)["rows"] if r["low"]}
    assert "Charger" in low and "Cable" in low                            # accessories keep their own rule
    assert "Glass" not in low and "Tecno Spark 20" not in low and "Nokia 105" not in low   # 1 phone / 0 phones
    rep = B.low_stock_report(db)
    names = {r[1] for r in rep["rows"]}
    assert names >= {"Charger", "Cable"} and not names & {"Tecno Spark 20", "Nokia 105"}
    assert reports.dashboard(db)["low_stock"] == len(names)
    assert not {r["name"] for r in reports.dashboard_extras(db)["low_items"]} & {"Tecno Spark 20", "Nokia 105"}
    assert not {r["name"] for r in reports.dashboard_lists(db)["low_stock"]} & {"Tecno Spark 20", "Nokia 105"}
    assert reports.is_low({"track_serial": 0, "low_stock_level": 2}, 2) and not reports.is_low(
        {"track_serial": 1, "low_stock_level": 2}, 0)


# ---------- Phones in Stock: edit and delete ----------
def _phone_stock(db, sup):
    smart = masters.add_product(db, "Note 40 Pro", 29000, category="Mobile Phone", mobile_type="smartphone",
                                ram_gb=8, storage_gb=256, brand="Infinix")
    trading.create_purchase(db, sup, [{"product_id": smart, "qty": 3, "price": 25000, "serials": [P1, P2, P3]}],
                            paid=75000)
    return smart, {r["imei1"]: r for r in PH.in_stock(db)}


def test_edit_a_phone_that_shares_its_line_moves_it_alone(shop):
    db, sup, cust, _ = shop
    smart, rows = _phone_stock(db, sup)
    inv = trading.create_invoice(db, cust, [{"product_id": smart, "qty": 1, "price": 29000, "serial": P3}], paid=29000)
    value_before = reports.stock_position(db)["total_value"]
    msg = PH.edit_phone(db, rows[P1]["serial_id"], "Note 40 Pro", P1, 24000, 28000, imei2=U3, brand="Infinix",
                            mobile_type="smartphone", ram_gb=12, storage_gb=256, condition="used")
    assert "ram_gb: 8 -> 12" in msg and "purchase rate: 25000 -> 24000" in msg
    now_ = {r["imei1"]: r for r in PH.in_stock(db)}
    a, b = now_[P1], now_[P2]
    assert (a["ram_gb"], a["storage_gb"], a["condition"], a["imei2"]) == (12, 256, "used", U3)
    assert (a["purchase_price"], a["sale_price"]) == (24000, 28000)
    assert (b["ram_gb"], b["purchase_price"], b["sale_price"], b["condition"]) == (8, 25000, 29000, "new")   # untouched
    assert a["product_id"] != smart and b["product_id"] == smart
    assert db.one("SELECT imei_mode FROM products WHERE id=?", (a["product_id"],))["imei_mode"] == "double"
    assert stock_qty(db.conn, smart) == 1 and stock_qty(db.conn, a["product_id"]) == 1
    assert reports.dashboard(db)["phones_in_stock"] == 2
    assert reports.stock_position(db)["total_value"] == value_before - 1000      # 25,000 -> 24,000
    # the sold phone, its invoice and the purchase keep their own prices and names
    assert trading.invoice_profit(db, inv) == 4000
    assert db.one("SELECT product_id FROM serials WHERE serial=?", (P3,))["product_id"] == smart
    assert db.one("SELECT price FROM purchase_items WHERE product_id=?", (smart,))["price"] == 25000
    # sold later through the normal invoice: profit uses the corrected rate
    inv2 = trading.create_invoice(db, cust, [{"product_id": a["product_id"], "qty": 1, "price": 28000,
                                              "serial": P1, "serial2": U3}], paid=28000)
    assert trading.invoice_profit(db, inv2) == 4000
    # the phone ledger explains the move
    kinds = [m["ref_type"] for m in reports.product_ledger(db, smart)["rows"]]
    assert "phone_edit" in kinds


def test_edit_a_phone_alone_in_its_line_and_validation(shop):
    db, sup, cust, _ = shop
    from app.services import used_phones
    rid = _used(db, U1, price=20000, sale=26000, mobile_type="smartphone", ram_gb=4, storage_gb=64)
    up = used_phones.detail(db, rid)
    row = {r["imei1"]: r for r in PH.in_stock(db)}[U1]
    PH.edit_phone(db, row["serial_id"], "Infinix Hot 40 Pro", U2, 21000, 27000, brand="Infinix",
                      mobile_type="smartphone", ram_gb=8, storage_gb=128, condition="used")
    p = db.one("SELECT * FROM products WHERE id=?", (up["product_id"],))           # its own line is corrected
    assert (p["name"], p["ram_gb"], p["storage_gb"], p["avg_cost"], p["sale_price"]) == ("Infinix Hot 40 Pro", 8, 128, 21000, 27000)
    up2 = used_phones.detail(db, rid)                                              # 2nd-hand record follows the IMEI
    assert up2["imei1"] == U2 and up2["status"] == "In stock" and up2["sale_price"] == 27000
    sid = row["serial_id"]
    for bad in (dict(name=" "), dict(imei1="12x"), dict(purchase_rate=-5), dict(sale_price=-1),
                dict(imei1=U2, imei2=U2), dict(ram_gb=0)):
        args = {"name": "X", "imei1": U2, "purchase_rate": 1, "sale_price": 1, "mobile_type": "smartphone",
                "ram_gb": 8, "storage_gb": 128, **bad}
        with pytest.raises(BusinessError):
            PH.edit_phone(db, sid, args.pop("name"), args.pop("imei1"), args.pop("purchase_rate"),
                              args.pop("sale_price"), **args)
    other = _used(db, U3, price=1000, sale=2000, model="Nokia 105", mobile_type="keypad")
    with pytest.raises(BusinessError):                                             # IMEI of another phone
        PH.edit_phone(db, sid, "X", U3, 1, 1, mobile_type="smartphone", ram_gb=8, storage_gb=128)
    PH.edit_phone(db, sid, "Infinix Hot 40 Pro", U2, 21000, 27000, mobile_type="keypad")   # keypad: no sizes
    assert db.one("SELECT ram_gb, mobile_type FROM products WHERE id=?", (up["product_id"],)) == {"ram_gb": None,
                                                                                               "mobile_type": "keypad"}
    assert other


def test_delete_a_phone_from_stock(shop):
    db, sup, cust, _ = shop
    smart, rows = _phone_stock(db, sup)
    value_before, cash_before = reports.stock_position(db)["total_value"], reports.cash_in_hand(db)
    with pytest.raises(BusinessError):                                             # a reason is required
        PH.remove_phone(db, rows[P2]["serial_id"], " ")
    PH.remove_phone(db, rows[P2]["serial_id"], "Entered by mistake")
    left = {r["imei1"] for r in PH.in_stock(db)}
    assert left == {P1, P3} and reports.dashboard(db)["phones_in_stock"] == 2 and stock_qty(db.conn, smart) == 2
    assert reports.stock_position(db)["total_value"] == value_before - 25000
    assert reports.cash_in_hand(db) == cash_before                                 # no money moves
    assert db.one("SELECT price FROM purchase_items WHERE product_id=?", (smart,))["price"] == 25000
    move = db.one("SELECT * FROM stock_moves WHERE ref_type='phone_removed'")
    assert P2 in move["note"] and "Entered by mistake" in move["note"] and move["qty"] == -1
    assert db.scalar("SELECT COUNT(*) FROM audit_log WHERE action='Phone removed from stock'") == 1
    with pytest.raises(BusinessError):                                             # already gone
        PH.remove_phone(db, rows[P2]["serial_id"], "again")
    inv = trading.create_invoice(db, cust, [{"product_id": smart, "qty": 1, "price": 29000, "serial": P1}], paid=29000)
    with pytest.raises(BusinessError):                                             # a sold phone cannot be removed
        PH.remove_phone(db, rows[P1]["serial_id"], "test")
    with pytest.raises(BusinessError):
        PH.edit_phone(db, rows[P1]["serial_id"], "X", P1, 1, 1)
    assert inv
    # the same IMEI can be entered again correctly afterwards
    trading.create_purchase(db, sup, [{"product_id": smart, "qty": 1, "price": 25000, "serials": [P2]}], paid=25000)
    assert P2 in {r["imei1"] for r in PH.in_stock(db)}


# ---------- Android app: business figures ----------
def test_business_overview_matches_the_windows_figures(shop):
    from datetime import date
    from app.services import business_overview as BO, loans
    db, sup, cust, _ = shop
    smart, rows = _phone_stock(db, sup)
    charger = masters.add_product(db, "Charger", 800, purchase_price=400, category="Accessories", low_stock_level=5)
    cable = masters.add_product(db, "Cable", 300, category="Accessories", low_stock_level=2)
    trading.create_purchase(db, sup, [{"product_id": charger, "qty": 4, "price": 400}], paid=1000)   # owes 600
    trading.create_invoice(db, cust, [{"product_id": smart, "qty": 1, "price": 29000, "serial": P3},
                                      {"product_id": charger, "qty": 1, "price": 800}], paid=20000)    # owes 9,800
    payments.add_expense(db, "Rent", 1000)
    loans.give_loan(db, "Rashid", 500)
    o = BO.overview(db)
    st, mo, sa, pu, fi, ac = (o[k] for k in ("stock", "mobiles", "sales", "purchases", "finance", "activity"))
    sp = reports.stock_position(db)
    assert st["purchase_value"] == sp["total_value"] == 2 * 25000 + 3 * 400
    assert (st["items"], st["quantity"]) == (2, 5) and st["sale_value"] == 2 * 29000 + 3 * 800
    assert (st["low_count"], st["out_count"]) == (1, 2)          # Charger low; Cable + Samsung A15 (fixture) finished
    assert {c["category"] for c in st["categories"]} == {"Mobile Phone", "Accessories"}
    assert sum(c["purchase_value"] for c in st["categories"]) == st["purchase_value"]
    assert mo["total"] == 2 == reports.dashboard(db)["phones_in_stock"]
    assert {p["imei1"] for p in mo["phones"]} == {P1, P2}                           # the sold phone is not there
    assert mo["brands"] == [{"brand": "Infinix", "qty": 2}] and mo["models"][0]["qty"] == 2
    ph = mo["phones"][0]
    assert (ph["ram_gb"], ph["storage_gb"], ph["purchase_price"], ph["sale_price"]) == (8, 256, 25000, 29000)
    today = date.today().isoformat()
    assert sa["today_total"] == 29800 and sa["today_count"] == 1 and sa["all_count"] == 1
    assert sa["month_total"] == 29800 and sa["today_list"][0]["customer"] == "Ali" and len(sa["monthly"]) == 12
    assert sa["monthly"][-1]["total"] == 29800
    assert pu["today_total"] == 75000 + 1600 == pu["month_total"] == pu["all_total"] and len(pu["recent"]) == 2
    pl = reports.profit_loss(db, today, today)
    assert fi == {"receivables": 9800, "payables": 600, "today_profit": pl["net_profit"],
                  "month_profit": reports.profit_loss(db, date.today().replace(day=1).isoformat(), today)["net_profit"],
                  "cash_in_hand": reports.cash_in_hand(db)}
    assert pl["net_profit"] == (29800 - 25000 - 400) - 1000
    assert ac["sales"][0]["amount"] == 29800 and ac["purchases"][0]["amount"] == 1600
    assert any("Charger" in a["text"] for a in ac["new_products"]) and ac["stock_updates"][0]["kind"] == "Sale"
    phone = _paired(db)
    synced = phone.ask(db, "sync")["data"]
    assert synced["overview"]["mobiles"]["total"] == 2 and synced["business"]["business_name"] is not None
    assert phone.ask(db, "overview")["data"]["finance"]["receivables"] == 9800
    PH.remove_phone(db, rows[P1]["serial_id"], "lost")                          # follows every change
    assert phone.ask(db, "overview")["data"]["mobiles"]["total"] == 1


# ---------- two-way sync with the Android app: the computer's side ----------
def _op(op_id, kind, data, made_at="2026-11-26 10:00:00"):
    return {"op_id": op_id, "kind": kind, "made_at": made_at, "data": data}


def test_sync_push_applies_phone_transactions_with_windows_rules(shop):
    from app.services import sync_hub as H
    db, sup, cust, prod = shop
    trading.create_purchase(db, sup, [{"product_id": prod, "qty": 5, "price": 100}], paid=500)
    ops = [
        _op("dev1-0001", "customer_add", {"name": "Kamran", "phone": "03001234567"}),
        _op("dev1-0002", "sale", {"no": "MB1-00001", "party_id": {"op": "dev1-0001"},
                                  "items": [{"product_id": prod, "qty": 2, "price": 150}], "paid": 100}),
        _op("dev1-0003", "receipt", {"party_id": {"op": "dev1-0001"}, "amount": 20}),
        _op("dev1-0004", "sale_return", {"party_id": {"op": "dev1-0001"},
                                         "items": [{"product_id": prod, "qty": 1, "price": 150}]}),
        _op("dev1-0005", "purchase", {"party_id": sup, "items": [{"product_id": prod, "qty": 10, "price": 110}],
                                      "paid": 1100}),
        _op("dev1-0006", "purchase_return", {"party_id": sup, "items": [{"product_id": prod, "qty": 3, "price": 110}]}),
        _op("dev1-0007", "supplier_payment", {"party_id": sup, "amount": 100}),
        _op("dev1-0008", "expense", {"category": "Tea", "amount": 80, "note": "from phone"}),
    ]
    res = H.push(db, "dev1", "MB1", ops)
    assert [r["status"] for r in res] == ["applied"] * 8, res
    kamran = res[0]["doc_id"]
    inv = db.one("SELECT * FROM invoices WHERE no='MB1-00001'")
    assert inv and inv["party_id"] == kamran and inv["date"] == "2026-11-26 10:00:00" and inv["paid"] == 100
    assert stock_qty(db.conn, prod) == 5 - 2 + 1 + 10 - 3
    bal = {r["id"]: r["balance"] for r in reports.all_balances(db, "customer")["rows"]}
    assert bal[kamran] == 300 - 100 - 20 - 150
    sb = {r["id"]: r["balance"] for r in reports.all_balances(db, "supplier")["rows"]}
    assert sb[sup] == -330 - 100                                          # returned 330 after paying, then paid 100
    assert db.scalar("SELECT COUNT(*) FROM expenses WHERE note='from phone'") == 1
    # the computer's own numbering is untouched by the phone's series
    assert trading.suggest_invoice_no(db) == "INV-00001"
    pc = trading.create_invoice(db, cust, [{"product_id": prod, "qty": 1, "price": 150}], paid=150)
    assert db.one("SELECT no FROM invoices WHERE id=?", (pc,))["no"] == "INV-00001"
    # the same transactions sent again (connection broke before the answer): nothing is applied twice
    again = H.push(db, "dev1", "MB1", ops)
    assert [r["doc_id"] for r in again] == [r["doc_id"] for r in res]
    assert stock_qty(db.conn, prod) == 10 and db.scalar("SELECT COUNT(*) FROM invoices") == 2


def test_sync_push_keeps_conflicts_and_allows_real_shortage(shop):
    from app.services import sync_hub as H
    db, sup, cust, prod = shop
    phone = masters.add_product(db, "Tecno Spark", 30000, category="Mobile Phone", mobile_type="smartphone",
                                ram_gb=8, storage_gb=128)
    trading.create_purchase(db, sup, [{"product_id": prod, "qty": 1, "price": 100},
                                      {"product_id": phone, "qty": 1, "price": 25000, "serials": [P1]}], paid=25100)
    # the computer sells the last accessory and the phone while the phone app is offline...
    trading.create_invoice(db, cust, [{"product_id": prod, "qty": 1, "price": 150},
                                      {"product_id": phone, "qty": 1, "price": 30000, "serial": P1}], paid=30150)
    # ...and the phone app sold them too
    res = H.push(db, "dev1", "MB1", [
        _op("dev1-0101", "sale", {"no": "MB1-00001", "party_id": cust,
                                  "items": [{"product_id": prod, "qty": 1, "price": 150}], "paid": 150}),
        _op("dev1-0102", "sale", {"no": "MB1-00002", "party_id": cust,
                                  "items": [{"product_id": phone, "qty": 1, "price": 30000, "serial": P1}], "paid": 30000}),
        _op("dev1-0103", "receipt", {"party_id": {"op": "dev1-9999"}, "amount": 5}),
        _op("dev1-0104", "sale", {"no": "INV-00099", "party_id": cust, "items": [], "paid": 0}),
        {"op_id": "x", "kind": "sale"},
    ])
    assert res[0]["status"] == "applied" and "below zero" in res[0]["message"]     # sale kept; shortage visible
    assert stock_qty(db.conn, prod) == -1
    assert res[1]["status"] == "conflict" and "already sold" in res[1]["message"]  # same IMEI: owner decides
    assert res[2]["status"] == "conflict" and res[3]["status"] == "conflict" and res[4]["status"] == "conflict"
    assert db.scalar("SELECT COUNT(*) FROM invoices WHERE no='MB1-00002'") == 0
    con = H.conflicts(db)
    assert {c["op_id"] for c in con} == {"dev1-0102", "dev1-0103", "dev1-0104"}
    assert next(c for c in con if c["op_id"] == "dev1-0102")["data"]["items"][0]["serial"] == P1   # kept in full
    H.dismiss_conflict(db, "dev1-0102")
    assert {c["op_id"] for c in H.conflicts(db)} == {"dev1-0103", "dev1-0104"}
    assert len(H.conflicts(db, include_dismissed=True)) == 3
    # a conflict sent again stays a conflict (never applied behind the owner's back)
    assert H.push(db, "dev1", "MB1", [_op("dev1-0102", "sale", {})])[0]["status"] == "dismissed"


def test_sync_pull_is_incremental_and_follows_changes(shop):
    from app.services import sync_hub as H
    db, sup, cust, prod = shop
    trading.create_purchase(db, sup, [{"product_id": prod, "qty": 4, "price": 100}], paid=400)
    m1 = H.manifest(db)
    assert set(m1) == set(H.KINDS) and len(m1["invoice"]) == 0 and len(m1["purchase"]) == 1
    have = {k: dict(map(tuple, v)) for k, v in m1.items()}
    inv = trading.create_invoice(db, cust, [{"product_id": prod, "qty": 1, "price": 150}], paid=150)
    m2 = {k: dict(map(tuple, v)) for k, v in H.manifest(db).items()}
    changed = {k: [i for i, fp in v.items() if have[k].get(i) != fp] for k, v in m2.items()}
    assert changed["invoice"] == [inv] and changed["purchase"] == [] and changed["product"] == [prod]
    got = H.fetch(db, changed)
    rec = got["invoice"][0]
    assert rec["no"] == "INV-00001" and rec["lines"][0]["qty"] == 1 and rec["_fp"] == m2["invoice"][inv]
    assert got["product"][0]["qty"] == 3
    trading.cancel_invoice(db, inv)                                      # a change on the computer...
    m3 = {k: dict(map(tuple, v)) for k, v in H.manifest(db).items()}
    assert m3["invoice"][inv] != m2["invoice"][inv]                     # ...is noticed and fetched again
    assert H.fetch(db, {"invoice": [inv]})["invoice"][0]["status"] == "cancelled"
    assert H.fetch(db, {"meta": [1]})["meta"][0]["dashboard"]["phones_in_stock"] == 0
    big = H.fetch(db, {"product": list(range(1, 1000)), "party": [1]})
    assert sum(len(v) for v in big.values()) <= H.MAX_FETCH


def test_sync_through_the_encrypted_api(shop):
    db, sup, cust, prod = shop
    trading.create_purchase(db, sup, [{"product_id": prod, "qty": 2, "price": 100}], paid=200)
    phone = _paired(db)
    h = phone.ask(db, "sync_hello")["data"]
    assert h["series"] == "MB1"
    other = _Phone("second-phone-0002")
    from app.services import companion as C
    pairing = C.Pairing()
    C.pair(db, pairing, other.pair_body(C.hello(db), pairing.start()))
    assert other.ask(db, "sync_hello")["data"]["series"] == "MB2"       # each phone its own series
    assert phone.ask(db, "sync_hello")["data"]["series"] == "MB1"
    r = phone.ask(db, "sync_push", ops=[_op("phone1-000001", "sale", {"no": "MB1-00001", "party_id": cust,
                                                            "items": [{"product_id": prod, "qty": 1, "price": 150}],
                                                            "paid": 150})])
    assert r["data"][0]["status"] == "applied"
    bad = other.ask(db, "sync_push", ops=[_op("phone2-000001", "sale", {"no": "MB1-00002", "party_id": cust,
                                                              "items": [{"product_id": prod, "qty": 1, "price": 150}],
                                                              "paid": 150})])
    assert bad["data"][0]["status"] == "conflict"                       # a phone cannot use another's series
    man = phone.ask(db, "sync_manifest")["data"]
    assert len(man["invoice"]) == 1
    assert phone.ask(db, "sync_fetch", want={"invoice": [man["invoice"][0][0]]})["data"]["invoice"][0]["no"] == "MB1-00001"


# ---------- the Android sync engine (Java) against the real Windows program: the 7 scenarios ----------
class _JavaPhone:
    """Runs android/.../sync/Engine.java on a desktop JVM (tests/java/SyncHarness.java) and talks to it.
    While it waits for an answer it also does the Windows program's work (the server hands jobs to this thread,
    like the real program's main thread)."""

    def __init__(self, classes, jobs):
        import queue, subprocess, threading
        self.jobs, self.lines = jobs, queue.Queue()
        self.proc = subprocess.Popen(["java", "-Dfile.encoding=UTF-8", "-Dstdout.encoding=UTF-8", "-Dstdin.encoding=UTF-8",
                                      "-cp", str(classes), "SyncHarness"], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1,
                                     encoding="utf-8")
        threading.Thread(target=lambda: [self.lines.put(l) for l in self.proc.stdout], daemon=True).start()

    def __call__(self, cmd):
        import json, queue
        self.proc.stdin.write(cmd + "\n")
        self.proc.stdin.flush()
        while True:
            try:
                return json.loads(self.lines.get(timeout=0.01))
            except queue.Empty:
                pass
            try:
                job, box = self.jobs.get_nowait()
            except queue.Empty:
                continue
            try:
                box["result"] = job()
            except BaseException as exc:
                box["error"] = exc
            box["done"].set()

    def out(self, cmd):
        r = self(cmd)
        assert r["ok"], (cmd, r)
        return r["out"]

    def record(self, kind, data):
        import json
        return self(f"record {kind} {json.dumps(data)}")

    def close(self):
        self.proc.kill()


@pytest.fixture
def java_phone(shop, tmp_path):
    import queue, shutil, subprocess, threading
    if not shutil.which("javac"):
        pytest.skip("no Java compiler here")
    from app.services import companion as C
    from app.services.companion_server import CompanionServer
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = os.path.join(root, "android", "app", "src", "main", "java", "com", "burhannexus", "companion")
    files = [os.path.join(src, "Crypto.java")] + [os.path.join(src, "sync", f) for f in os.listdir(os.path.join(src, "sync"))
                                                  if f != "SqliteStore.java"]       # (needs Android itself)
    subprocess.run(["javac", "-nowarn", "-d", str(tmp_path), *files, os.path.join(root, "tests", "java", "SyncHarness.java")],
                   check=True, capture_output=True)
    db = shop[0]
    jobs = queue.Queue()

    def run(job):
        if threading.current_thread() is threading.main_thread():
            return job()
        box = {"done": threading.Event()}
        jobs.put((job, box))
        assert box["done"].wait(20)
        if "error" in box:
            raise box["error"]
        return box["result"]

    pairing = C.Pairing()
    srv = CompanionServer(run, lambda: db, pairing, http_port=0, discovery_port=0, host="127.0.0.1")
    assert srv.start()
    phone = _JavaPhone(tmp_path, jobs)
    assert phone.out(f"pair 127.0.0.1 {srv.http_port} {pairing.start()} androidtest01") == "paired"
    yield phone
    phone.close()
    srv.stop()


def _by(rows, key, value):
    return next(r for r in rows if r[key] == value)


def test_android_scenarios_against_windows(shop, java_phone):
    import json
    db, sup, cust, prod = shop
    ph = java_phone
    tecno = masters.add_product(db, "Tecno Spark 20", 30000, category="Mobile Phone", mobile_type="smartphone",
                                ram_gb=8, storage_gb=128)
    trading.create_purchase(db, sup, [{"product_id": prod, "qty": 10, "price": 100},
                                      {"product_id": tecno, "qty": 2, "price": 25000, "serials": [P1, P2]}], paid=50000)
    assert ph.out("sync").startswith("true")
    assert ph.out("state") == "Connected – Auto Sync Active"
    stock = lambda pid: _by(ph.out("products"), "id", pid)["qty"]
    bal = lambda kind, pid: _by(ph.out("parties " + kind), "id", pid)["balance"]
    assert stock(prod) == 10 and len(ph.out(f"phones {tecno}")) == 2

    # Scenario 1: a sale on Android reaches Windows; stock and customer balance follow
    r = ph.out("record sale " + json.dumps({"party_id": cust, "items": [{"product_id": prod, "qty": 2, "price": 150}],
                                            "paid": 100}))
    assert r["no"] == "MB1-00001"
    assert stock(prod) == 8 and bal("customer", cust) == 200                    # shown on the phone at once
    assert _by(ph.out("docs invoice"), "no", "MB1-00001")["sync"] == "pending"
    ph.out("sync")
    inv = db.one("SELECT * FROM invoices WHERE no='MB1-00001'")
    assert inv and inv["total"] == 300 and inv["paid"] == 100
    assert stock_qty(db.conn, prod) == 8
    assert {r["id"]: r["balance"] for r in reports.all_balances(db, "customer")["rows"]}[cust] == 200
    assert reports.dashboard(db)["today_sales"] >= 300                          # Windows dashboard figures
    assert stock(prod) == 8 and bal("customer", cust) == 200                    # not counted twice after sync
    assert _by(ph.out("docs invoice"), "no", "MB1-00001")["sync"] == "synced"

    # Scenario 2: a purchase on Windows reaches Android
    trading.create_purchase(db, sup, [{"product_id": prod, "qty": 5, "price": 100}], paid=500)
    ph.out("sync")
    assert stock(prod) == 13 and any(d["total"] == 500 for d in ph.out("docs purchase"))

    # Scenario 3: a sales return on Android (a phone with its IMEI too)
    trading.create_invoice(db, cust, [{"product_id": tecno, "qty": 1, "price": 30000, "serial": P1}], paid=30000)
    ph.out("sync")
    assert len(ph.out(f"phones {tecno}")) == 1
    ph.out("record sale_return " + json.dumps({"party_id": cust, "items": [
        {"product_id": prod, "qty": 1, "price": 150}, {"product_id": tecno, "qty": 1, "price": 30000, "serial": P1}],
        "refunded": 30000}))
    assert stock(prod) == 14 and len(ph.out(f"phones {tecno}")) == 2 and bal("customer", cust) == 50
    ph.out("sync")
    assert stock_qty(db.conn, prod) == 14 and db.one("SELECT status FROM serials WHERE serial=?", (P1,))["status"] == "in_stock"
    assert {r["id"]: r["balance"] for r in reports.all_balances(db, "customer")["rows"]}[cust] == 50
    assert stock(prod) == 14 and bal("customer", cust) == 50

    # Scenario 4: a purchase return on Windows reaches Android
    sup_before = bal("supplier", sup)
    trading.purchase_return(db, sup, [{"product_id": prod, "qty": 3, "price": 100}], received=0)
    ph.out("sync")
    assert stock(prod) == 11 and bal("supplier", sup) == sup_before - 300

    # Scenario 5: computer off; sales, purchases, returns, payments, expense and a new customer on the phone
    ph.out("offline true")
    assert ph.out("sync").startswith("false")
    assert ph.out("state") in ("Offline Mode – Changes Saved Locally", "Sync Retry Pending")
    new = ph.out("record customer_add " + json.dumps({"name": "Kamran", "phone": "03001234567"}))
    kam = {"op": new["op_id"]}
    for kind, data in [
        ("sale", {"party_id": kam, "items": [{"product_id": prod, "qty": 3, "price": 150}], "paid": 0}),
        ("receipt", {"party_id": kam, "amount": 100}),
        ("purchase", {"party_id": sup, "items": [{"product_id": prod, "qty": 6, "price": 100},
                                                  {"product_id": tecno, "qty": 1, "price": 24000, "serials": [[P3]]}],
                      "paid": 0}),
        ("purchase_return", {"party_id": sup, "items": [{"product_id": prod, "qty": 1, "price": 100}]}),
        ("supplier_payment", {"party_id": sup, "amount": 1000}),
        ("expense", {"category": "Tea", "amount": 50}),
    ]:
        assert ph.record(kind, data)["ok"], (kind, ph.record)
    kam_key = "op:" + new["op_id"]
    assert stock(prod) == 11 - 3 + 6 - 1 and bal("customer", kam_key) == 350
    assert len(ph.out(f"phones {tecno}")) == 3
    ph.out("restart")                                                           # app closed and opened again
    assert stock(prod) == 13 and len([o for o in ph.out("ops") if o["status"] == "pending"]) == 7
    ph.out("offline false")
    assert ph.out("sync").startswith("true")
    assert all(o["status"] == "done" for o in ph.out("ops")), ph.out("ops")
    k = db.one("SELECT id FROM parties WHERE name='Kamran'")["id"]
    assert {r["id"]: r["balance"] for r in reports.all_balances(db, "customer")["rows"]}[k] == 350
    assert stock_qty(db.conn, prod) == 13 and db.one("SELECT status FROM serials WHERE serial=?", (P3,))["status"] == "in_stock"
    assert db.scalar("SELECT COUNT(*) FROM expenses WHERE category='Tea'") == 1
    assert stock(prod) == 13 and bal("customer", k) == 350
    assert not any(p["id"] == kam_key for p in ph.out("parties customer"))   # the phone's temporary copy is gone

    # Scenario 6: both work while disconnected, then meet
    ph.out("offline true")
    trading.create_invoice(db, cust, [{"product_id": prod, "qty": 4, "price": 150}], paid=600)   # Windows sells 4
    trading.create_invoice(db, cust, [{"product_id": tecno, "qty": 1, "price": 30000, "serial": P2}], paid=30000)
    assert ph.record("sale", {"party_id": cust, "items": [{"product_id": prod, "qty": 5, "price": 150}],
                              "paid": 750})["ok"]                                # the phone sells 5
    assert ph.record("sale", {"party_id": cust, "items": [{"product_id": tecno, "qty": 1, "price": 29000,
                                                           "serial": P2}], "paid": 29000})["ok"]   # same IMEI!
    ph.out("offline false")
    ph.out("sync")
    assert stock_qty(db.conn, prod) == 13 - 4 - 5 and stock(prod) == 4          # both sales kept, same result
    ops = ph.out("ops")
    assert [o["status"] for o in ops[-2:]] == ["done", "conflict"]              # double-sold phone: owner decides
    assert "already sold" in ops[-1]["message"]
    from app.services import sync_hub
    assert len(sync_hub.conflicts(db)) == 1                                       # kept on Windows too
    nos = [r["no"] for r in db.query("SELECT no FROM invoices ORDER BY id")]
    assert len(nos) == len(set(nos)) and "MB1-00003" in nos and "MB1-00004" not in nos

    # Scenario 7: the connection breaks after the computer saved the push but before the phone got the answer
    assert ph.record("sale", {"party_id": cust, "items": [{"product_id": prod, "qty": 1, "price": 150}], "paid": 150})["ok"]
    ph.out("break_after sync_push")
    assert ph.out("sync").startswith("false")
    assert ph.out("state") == "Sync Retry Pending"
    assert stock(prod) == 3                                                      # counted once, not twice
    assert ph.out("sync").startswith("true")                                     # retry: answered from the inbox
    assert db.scalar("SELECT COUNT(*) FROM invoices WHERE no='MB1-00005'") == 1 and stock_qty(db.conn, prod) == 3
    assert stock(prod) == 3
    ph.out("break_after sync_fetch")                                             # broken in the middle of the pull
    trading.create_invoice(db, cust, [{"product_id": prod, "qty": 3, "price": 150}], paid=450)
    assert ph.out("sync").startswith("false") and stock(prod) == 3               # nothing half-saved
    assert ph.out("sync").startswith("true") and stock(prod) == 0

    # what the phone refuses, like Windows does
    for kind, data in [("sale", {"party_id": cust, "items": [{"product_id": prod, "qty": 1, "price": 150}], "paid": 150}),
                       ("sale", {"party_id": 1, "items": [{"product_id": tecno, "qty": 1, "price": 1, "serial": P3}],
                                 "paid": 0}),
                       ("purchase", {"party_id": sup, "items": [{"product_id": tecno, "qty": 1, "price": 1,
                                                                 "serials": [[P3]]}], "paid": 0}),
                       ("receipt", {"party_id": cust, "amount": 0})]:
        r = ph.record(kind, data)
        assert not r["ok"] and r.get("invalid"), (kind, r)
    d = ph.out("dashboard")
    assert d["conflicts"] == 1 and d["unsent"] == 0 and d["phones_in_stock"] == reports.dashboard(db)["phones_in_stock"] == 2
    w = reports.dashboard(db)
    assert d["today_sales"] == w["today_sales"] and d["receivable"] == reports.all_balances(db, "customer")["total"]
