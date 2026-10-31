"""Shared helpers for services."""
from datetime import datetime


class BusinessError(Exception):
    """User-facing validation / business-rule error."""


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def r2(x) -> float:
    return round(float(x) + 0.0000001, 2) if x >= 0 else -round(abs(float(x)) + 0.0000001, 2)


def next_no(conn, prefix: str, width: int = 5) -> str:
    """Auto document number, e.g. INV-00001. Runs inside the caller's transaction."""
    row = conn.execute("SELECT value FROM counters WHERE name=?", (prefix,)).fetchone()
    val = (row["value"] if row else 0) + 1
    conn.execute("INSERT INTO counters(name,value) VALUES(?,?) "
                 "ON CONFLICT(name) DO UPDATE SET value=excluded.value", (prefix, val))
    return f"{prefix}-{val:0{width}d}"


def stock_qty(conn, product_id: int) -> float:
    r = conn.execute(
        "SELECT p.opening_stock + COALESCE((SELECT SUM(qty) FROM stock_moves "
        "WHERE product_id=p.id),0) AS q FROM products p WHERE p.id=?",
        (product_id,)).fetchone()
    if r is None:
        raise BusinessError("Product not found")
    return r["q"]


def customer_balance(conn, party_id: int) -> float:
    r = conn.execute(
        "SELECT p.opening_balance + COALESCE((SELECT SUM(debit-credit) FROM ledger "
        "WHERE party_id=p.id),0) AS b FROM parties p WHERE p.id=?", (party_id,)).fetchone()
    return r["b"]


def supplier_balance(conn, party_id: int) -> float:
    r = conn.execute(
        "SELECT p.opening_balance + COALESCE((SELECT SUM(credit-debit) FROM ledger "
        "WHERE party_id=p.id),0) AS b FROM parties p WHERE p.id=?", (party_id,)).fetchone()
    return r["b"]


def post_ledger(conn, party_id, date, ref_type, ref_id, debit=0.0, credit=0.0, note=None):
    if debit or credit:
        conn.execute("INSERT INTO ledger(party_id,date,debit,credit,ref_type,ref_id,note) "
                     "VALUES(?,?,?,?,?,?,?)",
                     (party_id, date, r2(debit), r2(credit), ref_type, ref_id, note))


def post_cash(conn, date, direction, amount, ref_type, ref_id, party_id=None, note=None):
    if amount and amount > 0:
        conn.execute("INSERT INTO cash_book(date,direction,amount,party_id,ref_type,ref_id,note) "
                     "VALUES(?,?,?,?,?,?,?)",
                     (date, direction, r2(amount), party_id, ref_type, ref_id, note))


def unpost(conn, ref_type: str, ref_id: int):
    """Remove every stock/ledger/cash row created by a document (used by cancel/edit)."""
    for table in ("stock_moves", "ledger", "cash_book"):
        conn.execute(f"DELETE FROM {table} WHERE ref_type=? AND ref_id=?", (ref_type, ref_id))
