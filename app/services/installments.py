"""Qist (installment) plans.

A plan splits part of what a customer owes into monthly installments. The customer's ledger is not
touched when a plan is made - the plan is only a schedule. Every cash recovery received from that
customer is counted automatically towards his oldest unpaid installment (see allocate())."""
from .common import BusinessError, add_months, audited, customer_balance, next_no, now, r2


def _schedule(principal: float, count: int, first_due: str):
    base = r2(principal / count)
    rows = []
    for i in range(count):
        amount = base if i < count - 1 else r2(principal - base * (count - 1))
        rows.append((i + 1, add_months(first_due[:10], i), amount))
    return rows


def preview(principal, count, first_due):
    if principal <= 0:
        raise BusinessError("Plan amount must be more than zero")
    if not 1 <= int(count) <= 60:
        raise BusinessError("Number of installments must be between 1 and 60")
    return _schedule(r2(principal), int(count), first_due)


@audited("Installment plan created", lambda db, a, k, r: db.scalar(
    "SELECT no||'  amount '||principal||' in '||count||' installments' FROM installment_plans WHERE id=?", (r,), ""))
def create_plan(db, party_id, principal, count, first_due, invoice_id=None, note="") -> int:
    sched = preview(principal, count, first_due)
    principal = r2(principal)
    with db.transaction() as c:
        party = c.execute("SELECT * FROM parties WHERE id=? AND kind='customer'", (party_id,)).fetchone()
        if not party or party["is_walkin"]:
            raise BusinessError("Choose a saved customer (not the walk-in customer)")
        if principal > customer_balance(c, party_id) + 0.005:
            raise BusinessError("The plan amount is more than this customer owes "
                                f"({customer_balance(c, party_id):,.2f})")
        if invoice_id:
            inv = c.execute("SELECT * FROM invoices WHERE id=? AND status='active'", (invoice_id,)).fetchone()
            if not inv or inv["party_id"] != party_id:
                raise BusinessError("This invoice does not belong to the customer")
            if c.execute("SELECT 1 FROM installment_plans WHERE invoice_id=? AND status='active'",
                         (invoice_id,)).fetchone():
                raise BusinessError("This invoice already has an installment plan")
        no = next_no(c, "QST")
        pid = c.execute("INSERT INTO installment_plans(no,date,party_id,invoice_id,principal,count,note) "
                        "VALUES(?,?,?,?,?,?,?)", (no, now(), party_id, invoice_id, principal, len(sched), note)).lastrowid
        for seq, due, amount in sched:
            c.execute("INSERT INTO installments(plan_id,seq,due_date,amount) VALUES(?,?,?,?)", (pid, seq, due, amount))
        return pid


def allocate(c, party_id, amount, date=None):
    """Called inside the receipt's transaction: money received goes to the oldest unpaid installments."""
    left = r2(amount)
    plans = c.execute("SELECT id FROM installment_plans WHERE party_id=? AND status='active' ORDER BY id",
                      (party_id,)).fetchall()
    for plan in plans:
        for ins in c.execute("SELECT * FROM installments WHERE plan_id=? AND amount-paid>0.004 ORDER BY seq",
                             (plan["id"],)).fetchall():
            if left <= 0.004:
                break
            take = min(left, r2(ins["amount"] - ins["paid"]))
            c.execute("UPDATE installments SET paid=? WHERE id=?", (r2(ins["paid"] + take), ins["id"]))
            left = r2(left - take)
        if not c.execute("SELECT 1 FROM installments WHERE plan_id=? AND amount-paid>0.004", (plan["id"],)).fetchone():
            c.execute("UPDATE installment_plans SET status='closed' WHERE id=?", (plan["id"],))
        if left <= 0.004:
            break


@audited("Installment plan cancelled", lambda db, a, k, r: f"plan id {a[0]}")
def cancel_plan(db, plan_id):
    with db.transaction() as c:
        plan = c.execute("SELECT * FROM installment_plans WHERE id=?", (plan_id,)).fetchone()
        if not plan or plan["status"] != "active":
            raise BusinessError("Only an active plan can be cancelled")
        if c.execute("SELECT 1 FROM installments WHERE plan_id=? AND paid>0", (plan_id,)).fetchone():
            raise BusinessError("Some installments are already paid, so this plan cannot be cancelled")
        c.execute("UPDATE installment_plans SET status='cancelled' WHERE id=?", (plan_id,))


def list_plans(db):
    return db.query(
        "SELECT p.*, pa.name AS customer, pa.phone, i.no AS invoice_no, "
        "(SELECT COALESCE(SUM(paid),0) FROM installments WHERE plan_id=p.id) AS paid, "
        "(SELECT MIN(due_date) FROM installments WHERE plan_id=p.id AND amount-paid>0.004) AS next_due "
        "FROM installment_plans p JOIN parties pa ON pa.id=p.party_id LEFT JOIN invoices i ON i.id=p.invoice_id "
        "ORDER BY (p.status='active') DESC, p.id DESC")


def schedule(db, plan_id):
    return db.query("SELECT * FROM installments WHERE plan_id=? ORDER BY seq", (plan_id,))


def due_list(db, today=None):
    """Unpaid installments of active plans, oldest due date first, with how late each is."""
    from datetime import date
    today = today or date.today().isoformat()
    rows = db.query(
        "SELECT ins.*, p.no AS plan_no, pa.name AS customer, pa.phone, pa.id AS party_id FROM installments ins "
        "JOIN installment_plans p ON p.id=ins.plan_id JOIN parties pa ON pa.id=p.party_id "
        "WHERE p.status='active' AND ins.amount-ins.paid>0.004 ORDER BY ins.due_date, ins.id")
    for r in rows:
        r["remaining"] = r2(r["amount"] - r["paid"])
        r["days_late"] = (date.fromisoformat(today) - date.fromisoformat(r["due_date"])).days
    return rows
