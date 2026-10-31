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
