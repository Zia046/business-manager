"""Cash received/paid, expenses and vouchers. Everything posts to the cash book."""
from .common import BusinessError, audited, next_no, now, post_cash, post_ledger, r2


def _amount(a) -> float:
    a = r2(a)
    if a <= 0:
        raise BusinessError("Amount must be greater than zero")
    return a


def _party(c, party_id, kind):
    p = c.execute("SELECT * FROM parties WHERE id=? AND kind=?", (party_id, kind)).fetchone()
    if not p:
        raise BusinessError(f"{kind.title()} not found")
    return p


def _voucher(c, kind, date, party_id, amount, ref_type, ref_id, note):
    no = next_no(c, "RV" if kind == "receipt" else "PV")
    c.execute("INSERT INTO vouchers(no,kind,date,party_id,amount,ref_type,ref_id,note) VALUES(?,?,?,?,?,?,?,?)",
              (no, kind, date, party_id, amount, ref_type, ref_id, note))
    return no


@audited("Cash received from customer", lambda db,a,k,r: f"{r}  amount {a[1] if len(a)>1 else k.get('amount')}  " + db.scalar("SELECT name FROM parties WHERE id=?",(a[0],),""))
def receive_from_customer(db, party_id, amount, note="", date=None) -> str:
    """Cash recovery: reduces what the customer owes. Returns the receipt voucher no."""
    date, amount = date or now(), _amount(amount)
    with db.transaction() as c:
        _party(c, party_id, "customer")
        ref = c.execute("INSERT INTO ledger(party_id,date,credit,ref_type,ref_id,note) VALUES(?,?,?,?,0,?)",
                        (party_id, date, amount, "receipt", note)).lastrowid
        c.execute("UPDATE ledger SET ref_id=? WHERE id=?", (ref, ref))
        post_cash(c, date, "in", amount, "receipt", ref, party_id, note)
        return _voucher(c, "receipt", date, party_id, amount, "receipt", ref, note)


@audited("Payment to supplier", lambda db,a,k,r: f"{r}  amount {a[1] if len(a)>1 else k.get('amount')}  " + db.scalar("SELECT name FROM parties WHERE id=?",(a[0],),""))
def pay_supplier(db, party_id, amount, note="", date=None) -> str:
    date, amount = date or now(), _amount(amount)
    with db.transaction() as c:
        _party(c, party_id, "supplier")
        ref = c.execute("INSERT INTO ledger(party_id,date,debit,ref_type,ref_id,note) VALUES(?,?,?,?,0,?)",
                        (party_id, date, amount, "payment", note)).lastrowid
        c.execute("UPDATE ledger SET ref_id=? WHERE id=?", (ref, ref))
        post_cash(c, date, "out", amount, "payment", ref, party_id, note)
        return _voucher(c, "payment", date, party_id, amount, "payment", ref, note)


@audited("Payment to customer", lambda db,a,k,r: f"{r}  amount {a[1] if len(a)>1 else k.get('amount')}  " + db.scalar("SELECT name FROM parties WHERE id=?",(a[0],),""))
def pay_customer(db, party_id, amount, note="", date=None) -> str:
    """Refund / payment made to a customer (increases what they are owed, i.e. lowers balance)."""
    date, amount = date or now(), _amount(amount)
    with db.transaction() as c:
        _party(c, party_id, "customer")
        ref = c.execute("INSERT INTO ledger(party_id,date,debit,ref_type,ref_id,note) VALUES(?,?,?,?,0,?)",
                        (party_id, date, amount, "customer_payment", note)).lastrowid
        c.execute("UPDATE ledger SET ref_id=? WHERE id=?", (ref, ref))
        post_cash(c, date, "out", amount, "customer_payment", ref, party_id, note)
        return _voucher(c, "payment", date, party_id, amount, "customer_payment", ref, note)


@audited("Expense", lambda db,a,k,r: f"{a[0]}  amount {a[1]}")
def add_expense(db, category, amount, note="", date=None) -> int:
    date, amount = date or now(), _amount(amount)
    if not category.strip():
        raise BusinessError("Expense category is required")
    with db.transaction() as c:
        eid = c.execute("INSERT INTO expenses(date,category,amount,note) VALUES(?,?,?,?)",
                        (date, category.strip(), amount, note)).lastrowid
        post_cash(c, date, "out", amount, "expense", eid, None, f"{category}: {note}")
        return eid


@audited("Expense deleted", lambda db,a,k,r: f"expense id {a[0]}")
def delete_expense(db, expense_id):
    with db.transaction() as c:
        c.execute("DELETE FROM cash_book WHERE ref_type='expense' AND ref_id=?", (expense_id,))
        c.execute("DELETE FROM expenses WHERE id=?", (expense_id,))


__all__ = ["post_ledger"]
