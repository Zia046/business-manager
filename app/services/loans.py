"""Cash loans given to people, and the money they bring back.

A person's balance = his loans - his repayments (- adjustments). Giving a loan takes cash out of the
drawer and a repayment puts it back, both through the cash book, so Cash in Hand always agrees.
These persons are kept apart from customers: a cash loan is never mixed into a customer's account,
so the Outstanding total can add both without counting anything twice."""
import re

from .common import BusinessError, audited, now, post_cash, r2

_BAL = ("COALESCE((SELECT SUM(CASE kind WHEN 'loan' THEN amount ELSE -amount END) FROM loan_entries "
        "WHERE person_id=p.id),0)")


def _amount(a) -> float:
    try:
        a = r2(float(a))
    except (TypeError, ValueError):
        raise BusinessError("Enter the amount as a number")
    if a <= 0:
        raise BusinessError("Amount must be greater than zero")
    return a


def clean_cnic(text) -> str:
    """'' or 13 digits written as 12345-1234567-1. Dashes and spaces may be typed or left out."""
    digits = re.sub(r"[\s-]", "", text or "")
    if not digits:
        return ""
    if not re.fullmatch(r"[0-9]{13}", digits):
        raise BusinessError("CNIC must have 13 digits (e.g. 15101-1234567-1)")
    return f"{digits[:5]}-{digits[5:12]}-{digits[12]}"


def balance(conn, person_id) -> float:
    r = conn.execute(f"SELECT {_BAL} AS b FROM loan_people p WHERE p.id=?", (person_id,)).fetchone()
    if r is None:
        raise BusinessError("Person not found")
    return r2(r["b"])


def _find_person(c, name, cnic, phone):
    if cnic:
        row = c.execute("SELECT * FROM loan_people WHERE cnic=?", (cnic,)).fetchone()
        if row:
            return row
    return c.execute("SELECT * FROM loan_people WHERE lower(name)=lower(?) AND COALESCE(phone,'')=? "
                     "AND (COALESCE(cnic,'')='' OR ?='')", (name, phone, cnic)).fetchone()


@audited("Cash loan given", lambda db,a,k,r: f"{a[0] if a else k.get('name')}  amount {a[1] if len(a)>1 else k.get('amount')}")
def give_loan(db, name, amount, cnic="", phone="", address="", note="", date=None, person_id=None) -> int:
    """Cash given to a person. The same person (same CNIC, or same name and mobile) gets every loan in one
    account. Returns the person's id."""
    name, phone, address = (name or "").strip(), (phone or "").strip(), (address or "").strip()
    amount, date, cnic = _amount(amount), date or now(), clean_cnic(cnic)
    if not name:
        raise BusinessError("Person name is required")
    with db.transaction() as c:
        person = (c.execute("SELECT * FROM loan_people WHERE id=?", (person_id,)).fetchone() if person_id
                  else _find_person(c, name, cnic, phone))
        if person_id and not person:
            raise BusinessError("Person not found")
        if person:
            pid = person["id"]
            c.execute("UPDATE loan_people SET name=?, cnic=?, phone=?, address=? WHERE id=?",
                      (name, cnic or person["cnic"], phone or person["phone"], address or person["address"], pid))
        else:
            pid = c.execute("INSERT INTO loan_people(name,cnic,phone,address) VALUES(?,?,?,?)",
                            (name, cnic, phone, address)).lastrowid
        eid = c.execute("INSERT INTO loan_entries(person_id,date,kind,amount,note) VALUES(?,?,'loan',?,?)",
                        (pid, date, amount, (note or "").strip())).lastrowid
        post_cash(c, date, "out", amount, "cash_loan", eid, None, f"{name}" + (f" - {note.strip()}" if note else ""))
        return pid


@audited("Cash loan repayment", lambda db,a,k,r: f"person id {a[0]}  amount {a[1] if len(a)>1 else k.get('amount')}  remaining {r}")
def receive_repayment(db, person_id, amount, note="", date=None) -> float:
    """Money brought back (all or a part). It can never be more than what the person still owes.
    Returns the remaining balance."""
    amount, date = _amount(amount), date or now()
    with db.transaction() as c:
        person = c.execute("SELECT * FROM loan_people WHERE id=?", (person_id,)).fetchone()
        if not person:
            raise BusinessError("Person not found")
        due = balance(c, person_id)
        if due <= 0:
            raise BusinessError(f"{person['name']} has no outstanding loan")
        if amount > due + 0.004:
            raise BusinessError(f"Amount is more than the outstanding loan ({due:,.2f})")
        eid = c.execute("INSERT INTO loan_entries(person_id,date,kind,amount,note) VALUES(?,?,'repayment',?,?)",
                        (person_id, date, amount, (note or "").strip())).lastrowid
        post_cash(c, date, "in", amount, "loan_repayment", eid, None,
                  person["name"] + (f" - {note.strip()}" if note else ""))
        return r2(due - amount)


def people(db, only_open=False, text=""):
    """One row per person: total given, total returned and what is still outstanding."""
    rows = db.query(
        "SELECT p.*, COALESCE((SELECT SUM(amount) FROM loan_entries WHERE person_id=p.id AND kind='loan'),0) AS given, "
        "COALESCE((SELECT SUM(amount) FROM loan_entries WHERE person_id=p.id AND kind<>'loan'),0) AS returned "
        "FROM loan_people p ORDER BY p.name")
    out, text = [], (text or "").strip().lower()
    for r in rows:
        r["given"], r["returned"] = r2(r["given"]), r2(r["returned"])
        r["balance"] = r2(r["given"] - r["returned"])
        if only_open and r["balance"] < 0.005:
            continue
        if text and text not in " ".join(str(r[k] or "") for k in ("name", "cnic", "phone", "address")).lower():
            continue
        out.append(r)
    return out


def history(db, person_id):
    """Every loan and repayment of one person, oldest first, with the balance after each line."""
    bal, out = 0.0, []
    for r in db.query("SELECT * FROM loan_entries WHERE person_id=? ORDER BY date, id", (person_id,)):
        bal += r["amount"] if r["kind"] == "loan" else -r["amount"]
        out.append({**r, "balance": r2(bal)})
    return out


def total_outstanding(db) -> float:
    return r2(db.scalar("SELECT COALESCE(SUM(CASE kind WHEN 'loan' THEN amount ELSE -amount END),0) "
                        "FROM loan_entries"))


def clear_all(c):
    """Reset > 'clear balances': every loan balance goes to zero with a visible adjustment line (no cash moves)."""
    stamp = now()
    for p in c.execute(f"SELECT p.id, {_BAL} AS b FROM loan_people p").fetchall():
        if p["b"] > 0.004:
            c.execute("INSERT INTO loan_entries(person_id,date,kind,amount,note) VALUES(?,?,'adjustment',?,?)",
                      (p["id"], stamp, r2(p["b"]), "Balance cleared (reset)"))
