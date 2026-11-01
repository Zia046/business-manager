"""Reset Database: erase chosen data, safely.

Safety: current password required, a written reason is required, a safety backup is made first,
and the action is written to reset_log.txt. The screen asks for two confirmations on top of this.
"""
from datetime import datetime
from pathlib import Path

from ..db.connection import DB_FILE, SALT_FILE
from . import backup
from .auth import BRANDING_FILE, verify_password
from .common import BusinessError, customer_balance, now, r2, supplier_balance

OPTIONS = {
    "transactions": "All transactions: sale invoices, purchases, returns, payments, expenses, vouchers, cash "
                    "book, stock movements and IMEI records (stock goes back to the opening stock)",
    "products": "Products (this also erases all transactions)",
    "customers": "Customers (this also erases all transactions)",
    "suppliers": "Suppliers (this also erases all transactions)",
    "balances": "Clear all outstanding / baqayajat balances to zero (accounts are kept)",
    "factory": "EVERYTHING: factory reset. Company details, username and password are erased too and the "
               "software asks for registration again",
}
NEEDS_TRANSACTIONS = {"products", "customers", "suppliers"}


def expand(options) -> set:
    """Resolve dependencies: products/customers/suppliers cannot be removed while transactions exist."""
    opts = set(options)
    if opts - set(OPTIONS):
        raise BusinessError("Unknown reset option")
    if "factory" in opts:
        return set(OPTIONS)
    if opts & NEEDS_TRANSACTIONS:
        opts.add("transactions")
    return opts


def reset_data(db, password, reason, options) -> dict:
    """Returns {'factory': bool, 'safety': Path, 'done': [..]}. After a factory reset `db` is closed
    and the program must close."""
    if not options:
        raise BusinessError("Select what you want to erase")
    reason = (reason or "").strip()
    if len(reason) < 5:
        raise BusinessError("Write the reason for the reset (at least 5 letters)")
    user = db.one("SELECT * FROM users LIMIT 1")
    if not password or not verify_password(password, user["pass_hash"]):
        raise BusinessError("Current password is incorrect")
    opts = expand(options)

    safety = backup.create_backup(db, prefix="before_reset")            # always keep a way back
    data_dir = Path(db.data_dir)
    with open(data_dir / "reset_log.txt", "a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} | user {user['login_id']} | erased: "
                f"{', '.join(sorted(options))} | reason: {reason} | safety backup: {safety.name}\n")

    if "factory" in opts:
        db.close()
        for name in (DB_FILE, SALT_FILE, BRANDING_FILE, backup.SETTINGS_FILE, "lock.json"):
            (data_dir / name).unlink(missing_ok=True)
        logo = data_dir / "logo"
        if logo.exists():
            for f in logo.iterdir():
                if f.is_file():
                    f.unlink()
        return {"factory": True, "safety": safety, "done": ["everything"]}

    done = []
    with db.transaction() as c:
        if "transactions" in opts:
            for table in ("invoice_items", "invoices", "purchase_items", "purchases", "return_items", "returns",
                          "serials", "stock_moves", "ledger", "cash_book", "expenses", "vouchers", "counters"):
                c.execute(f"DELETE FROM {table}")
            done.append("transactions")
        if "products" in opts:
            c.execute("DELETE FROM products")
            done.append("products")
        if "customers" in opts:
            c.execute("DELETE FROM parties WHERE kind='customer' AND is_walkin=0")
            done.append("customers")
        if "suppliers" in opts:
            c.execute("DELETE FROM parties WHERE kind='supplier'")
            done.append("suppliers")
        if "balances" in opts:
            _clear_balances(c)
            done.append("balances")
    return {"factory": False, "safety": safety, "done": done}


def _clear_balances(c):
    """Bring every customer/supplier balance to zero with a visible adjustment entry (history stays valid)."""
    stamp = now()
    for p in c.execute("SELECT id, kind FROM parties WHERE is_walkin=0").fetchall():
        bal = r2(customer_balance(c, p["id"]) if p["kind"] == "customer" else supplier_balance(c, p["id"]))
        if abs(bal) < 0.005:
            continue
        debit, credit = _adjustment(p["kind"], bal)
        c.execute("INSERT INTO ledger(party_id,date,debit,credit,ref_type,ref_id,note) VALUES(?,?,?,?,?,?,?)",
                  (p["id"], stamp, debit, credit, "adjustment", 0, "Balance cleared (reset)"))


def _adjustment(kind, bal):
    """(debit, credit) that brings a balance back to zero. `bal` is positive when the customer owes
    us / we owe the supplier."""
    if kind == "customer":
        return (0.0, bal) if bal > 0 else (-bal, 0.0)
    return (bal, 0.0) if bal > 0 else (0.0, -bal)
