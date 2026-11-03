"""Repair / service jobs: receive a phone, repair it, deliver it and take the money.

Money taken (advance and final payment) goes to the cash book. When a job is delivered its charges
count as repair income and its parts cost as repair cost in the Profit & Loss report."""
from .common import BusinessError, audited, next_no, now, post_cash, r2

OPEN = ("received", "in_progress", "ready")
STATUS_LABEL = {"received": "Received", "in_progress": "In repair", "ready": "Ready", "delivered": "Delivered",
                "cancelled": "Cancelled"}


def _money(v, label, allow_zero=True):
    try:
        v = r2(float(v or 0))
    except (TypeError, ValueError):
        raise BusinessError(f"{label} is not a valid amount")
    if v < 0 or (v == 0 and not allow_zero):
        raise BusinessError(f"{label} must be more than zero")
    return v


def _job(c, job_id):
    j = c.execute("SELECT * FROM repairs WHERE id=?", (job_id,)).fetchone()
    if not j:
        raise BusinessError("Repair job not found")
    return j


@audited("Repair job received", lambda db, a, k, r: db.scalar("SELECT no||'  '||device||'  '||customer_name "
                                                              "FROM repairs WHERE id=?", (r,), ""))
def create_job(db, customer_name, phone, device, problem, estimate=0, advance=0, imei="", note="") -> int:
    customer_name, device = (customer_name or "").strip(), (device or "").strip()
    if not customer_name:
        raise BusinessError("Customer name is required")
    if not device:
        raise BusinessError("Device (phone model) is required")
    estimate, advance = _money(estimate, "Estimate"), _money(advance, "Advance")
    if estimate and advance > estimate:
        raise BusinessError("Advance cannot be more than the estimate")
    date = now()
    with db.transaction() as c:
        no = next_no(c, "RJ")
        jid = c.execute("INSERT INTO repairs(no,date,customer_name,phone,device,imei,problem,estimate,received,note) "
                        "VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (no, date, customer_name, (phone or "").strip(), device, (imei or "").strip(),
                         (problem or "").strip(), estimate, advance, note)).lastrowid
        post_cash(c, date, "in", advance, "repair", jid, None, f"Repair advance {no}")
        return jid


@audited("Repair job updated", lambda db, a, k, r: f"job id {a[0]}")
def update_job(db, job_id, status=None, charges=None, parts_cost=None, estimate=None, problem=None, note=None):
    """Change the status of an open job (received / in_progress / ready) and the amounts."""
    with db.transaction() as c:
        j = _job(c, job_id)
        if j["status"] not in OPEN:
            raise BusinessError("A delivered or cancelled job cannot be changed")
        if status is not None and status not in OPEN:
            raise BusinessError("Use Deliver or Cancel for this status")
        fields = {}
        if status is not None:
            fields["status"] = status
        if charges is not None:
            fields["charges"] = _money(charges, "Charges")
        if parts_cost is not None:
            fields["parts_cost"] = _money(parts_cost, "Parts cost")
        if estimate is not None:
            fields["estimate"] = _money(estimate, "Estimate")
        if problem is not None:
            fields["problem"] = problem.strip()
        if note is not None:
            fields["note"] = note
        if fields:
            c.execute("UPDATE repairs SET " + ",".join(f"{k}=?" for k in fields) + " WHERE id=?",
                      (*fields.values(), job_id))


@audited("Repair job delivered", lambda db, a, k, r: f"job id {a[0]}  payment {a[3] if len(a) > 3 else k.get('payment')}")
def deliver(db, job_id, charges, parts_cost, payment) -> None:
    """Hand the phone back: final charges, what the parts cost us, and the money taken now."""
    charges, parts_cost, payment = _money(charges, "Charges"), _money(parts_cost, "Parts cost"), _money(payment, "Payment")
    date = now()
    with db.transaction() as c:
        j = _job(c, job_id)
        if j["status"] not in OPEN:
            raise BusinessError("This job is already delivered or cancelled")
        if j["received"] + payment > charges + 0.005:
            raise BusinessError(f"Total received would be more than the charges ({charges:,.2f})")
        c.execute("UPDATE repairs SET status='delivered', delivered_date=?, charges=?, parts_cost=?, received=? "
                  "WHERE id=?", (date, charges, parts_cost, r2(j["received"] + payment), job_id))
        post_cash(c, date, "in", payment, "repair", job_id, None, f"Repair {j['no']}")


@audited("Repair payment received", lambda db, a, k, r: f"job id {a[0]}  amount {a[1]}")
def receive_payment(db, job_id, amount):
    """Money taken later for a delivered job that was not fully paid."""
    amount = _money(amount, "Amount", allow_zero=False)
    with db.transaction() as c:
        j = _job(c, job_id)
        if j["status"] == "cancelled":
            raise BusinessError("This job was cancelled")
        if j["received"] + amount > j["charges"] + 0.005:
            raise BusinessError("This is more than the amount still due")
        c.execute("UPDATE repairs SET received=? WHERE id=?", (r2(j["received"] + amount), job_id))
        post_cash(c, now(), "in", amount, "repair", job_id, None, f"Repair {j['no']}")


@audited("Repair job cancelled", lambda db, a, k, r: f"job id {a[0]}")
def cancel_job(db, job_id):
    """Customer takes the phone back unrepaired: the advance (if any) is returned."""
    with db.transaction() as c:
        j = _job(c, job_id)
        if j["status"] not in OPEN:
            raise BusinessError("Only an open job can be cancelled")
        post_cash(c, now(), "out", j["received"], "repair", job_id, None, f"Advance returned {j['no']}")
        c.execute("UPDATE repairs SET status='cancelled', received=0 WHERE id=?", (job_id,))


def list_jobs(db, status=None, text=""):
    sql, args = "SELECT * FROM repairs WHERE 1=1", []
    if status == "open":
        sql += " AND status IN ('received','in_progress','ready')"
    elif status:
        sql += " AND status=?"
        args.append(status)
    if text.strip():
        sql += " AND (no LIKE ? OR customer_name LIKE ? OR phone LIKE ? OR device LIKE ? OR imei LIKE ?)"
        args += [f"%{text.strip()}%"] * 5
    jobs = db.query(sql + " ORDER BY id DESC LIMIT 500", tuple(args))
    for j in jobs:
        j["due"] = r2(max(j["charges"] - j["received"], 0)) if j["status"] != "cancelled" else 0.0
    return jobs


def repair_totals(db, date_from, date_to):
    """(income, parts_cost) of jobs delivered in the period - used by Profit & Loss."""
    a, b = date_from + " 00:00:00", date_to + " 23:59:59"
    row = db.one("SELECT COALESCE(SUM(charges),0) AS inc, COALESCE(SUM(parts_cost),0) AS cost FROM repairs "
                 "WHERE status='delivered' AND delivered_date BETWEEN ? AND ?", (a, b))
    return r2(row["inc"]), r2(row["cost"])
