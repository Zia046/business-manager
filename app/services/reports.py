"""Read-only report queries. The UI/PDF/Excel layers only format these results."""
from .common import r2

_END = " 23:59:59"
_START = " 00:00:00"


def cash_in_hand(db, upto=None) -> float:
    cond, p = ("AND date <= ?", (upto + _END,)) if upto else ("", ())
    sql = (f"SELECT COALESCE(SUM(CASE direction WHEN 'in' THEN amount ELSE -amount END),0) "
           f"FROM cash_book WHERE 1=1 {cond}")
    return r2(db.scalar("SELECT opening_cash FROM company WHERE id=1") + db.scalar(sql, p))


def cash_book(db, date_from, date_to):
    opening = r2(db.scalar("SELECT opening_cash FROM company WHERE id=1") + db.scalar(
        "SELECT COALESCE(SUM(CASE direction WHEN 'in' THEN amount ELSE -amount END),0) "
        "FROM cash_book WHERE date < ?", (date_from + _START,)))
    rows = db.query("SELECT c.*, p.name AS party_name FROM cash_book c LEFT JOIN parties p ON p.id=c.party_id "
                    "WHERE c.date BETWEEN ? AND ? ORDER BY c.date, c.id", (date_from + _START, date_to + _END))
    total_in = r2(sum(r["amount"] for r in rows if r["direction"] == "in"))
    total_out = r2(sum(r["amount"] for r in rows if r["direction"] == "out"))
    return {"opening": opening, "rows": rows, "total_in": total_in, "total_out": total_out,
            "closing": r2(opening + total_in - total_out)}


def customer_ledger(db, party_id, date_from=None, date_to=None):
    """Ledger of a customer or supplier. Also returns the balance at the start and end of the period."""
    party = db.one("SELECT * FROM parties WHERE id=?", (party_id,))
    sign = 1 if party["kind"] == "customer" else -1  # supplier: credit increases the balance
    bal = party["opening_balance"]
    period_opening, period_closing = bal, bal
    out = []
    for r in db.query("SELECT * FROM ledger WHERE party_id=? ORDER BY date, id", (party_id,)):
        bal += sign * (r["debit"] - r["credit"])
        if date_from and r["date"] < date_from + _START:
            period_opening = bal
            period_closing = bal
            continue
        if date_to and r["date"] > date_to + _END:
            continue
        period_closing = bal
        out.append({**r, "balance": r2(bal)})
    return {"party": party, "opening": party["opening_balance"], "rows": out, "closing": r2(bal),
            "period_opening": r2(period_opening), "period_closing": r2(period_closing)}


def all_balances(db, kind="customer"):
    """Outstanding / Baqayajat: parties with a non-zero balance."""
    sign = "debit-credit" if kind == "customer" else "credit-debit"
    rows = db.query(
        f"SELECT p.id, p.name, p.phone, p.opening_balance + COALESCE((SELECT SUM({sign}) FROM ledger "
        f"WHERE party_id=p.id),0) AS balance FROM parties p WHERE p.kind=? AND p.active=1 "
        f"AND p.is_walkin=0 ORDER BY p.name", (kind,))
    rows = [{**r, "balance": r2(r["balance"])} for r in rows if abs(r["balance"]) > 0.004]
    return {"rows": rows, "total": r2(sum(r["balance"] for r in rows))}


def stock_position(db):
    rows = db.query(
        "SELECT p.id, p.name, p.category, p.unit, p.avg_cost, p.sale_price, p.low_stock_level, "
        "p.opening_stock + COALESCE((SELECT SUM(qty) FROM stock_moves WHERE product_id=p.id),0) AS qty "
        "FROM products p WHERE p.active=1 ORDER BY p.name")
    for r in rows:
        r["value"] = r2(r["qty"] * r["avg_cost"])
        r["low"] = r["qty"] <= r["low_stock_level"]
    return {"rows": rows, "total_value": r2(sum(r["value"] for r in rows))}


def product_ledger(db, product_id, date_from=None, date_to=None):
    p = db.one("SELECT * FROM products WHERE id=?", (product_id,))
    bal, out = p["opening_stock"], []
    for m in db.query("SELECT * FROM stock_moves WHERE product_id=? ORDER BY date, id", (product_id,)):
        bal += m["qty"]
        if (not date_from or m["date"] >= date_from + _START) and (not date_to or m["date"] <= date_to + _END):
            out.append({**m, "balance": bal})
    return {"product": p, "opening": p["opening_stock"], "rows": out, "closing": bal}


def sale_summary(db, date_from, date_to, group="day"):
    fmt = "%Y-%m-%d" if group == "day" else "%Y-%m"
    rows = db.query(
        "SELECT strftime(?, date) AS period, COUNT(*) AS invoices, SUM(total) AS sales, SUM(paid) AS received "
        "FROM invoices WHERE status='active' AND date BETWEEN ? AND ? GROUP BY period ORDER BY period",
        (fmt, date_from + _START, date_to + _END))
    return {"rows": rows, "total": r2(sum(r["sales"] for r in rows))}


def invoice_wise_summary(db, date_from, date_to):
    return db.query(
        "SELECT i.id, i.no, i.date, p.name AS customer, i.total, i.paid, i.total-i.paid AS balance, "
        "i.total-i.cost_total AS profit FROM invoices i JOIN parties p ON p.id=i.party_id "
        "WHERE i.status='active' AND i.date BETWEEN ? AND ? ORDER BY i.date, i.id",
        (date_from + _START, date_to + _END))


def profit_loss(db, date_from, date_to):
    a, b = date_from + _START, date_to + _END
    sales = db.scalar("SELECT SUM(total) FROM invoices WHERE status='active' AND date BETWEEN ? AND ?", (a, b))
    cogs = db.scalar("SELECT SUM(cost_total) FROM invoices WHERE status='active' AND date BETWEEN ? AND ?", (a, b))
    ret = db.scalar("SELECT SUM(total) FROM returns WHERE kind='sale' AND date BETWEEN ? AND ?", (a, b))
    ret_cost = db.scalar("SELECT SUM(ri.qty*ri.unit_cost) FROM return_items ri JOIN returns r "
                         "ON r.id=ri.return_id WHERE r.kind='sale' AND r.date BETWEEN ? AND ?", (a, b))
    exp = db.scalar("SELECT SUM(amount) FROM expenses WHERE date BETWEEN ? AND ?", (a, b))
    net_sales, net_cogs = r2(sales - ret), r2(cogs - ret_cost)
    from .repairs import repair_totals
    rep_inc, rep_cost = repair_totals(db, date_from, date_to)
    gross = r2(net_sales - net_cogs + rep_inc - rep_cost)
    return {"sales": r2(sales), "sale_returns": r2(ret), "net_sales": net_sales,
            "cost_of_goods": net_cogs, "repair_income": rep_inc, "repair_cost": rep_cost,
            "gross_profit": gross, "expenses": r2(exp), "net_profit": r2(gross - exp)}


def balance_sheet(db):
    cash = cash_in_hand(db)
    stock = stock_position(db)["total_value"]
    recv = all_balances(db, "customer")["total"]
    pay = all_balances(db, "supplier")["total"]
    assets, liabilities = r2(cash + stock + recv), r2(pay)
    return {"cash": cash, "stock_value": stock, "receivables": recv, "total_assets": assets,
            "payables": pay, "total_liabilities": liabilities, "equity": r2(assets - liabilities)}


def invoice_detail(db, invoice_id):
    """Everything needed to print one invoice (company, customer, lines, totals)."""
    inv = db.one("SELECT * FROM invoices WHERE id=?", (invoice_id,))
    if not inv:
        return None
    items = db.query(
        "SELECT ii.*, p.name AS product_name, p.unit FROM invoice_items ii "
        "JOIN products p ON p.id=ii.product_id WHERE ii.invoice_id=? ORDER BY ii.id", (invoice_id,))
    party = db.one("SELECT * FROM parties WHERE id=?", (inv["party_id"],))
    from .common import customer_balance
    closing = customer_balance(db.conn, party["id"]) if not party["is_walkin"] else 0.0
    return {"invoice": inv, "items": items, "party": party,
            "company": db.one("SELECT * FROM company WHERE id=1"),
            "balance_due": r2(inv["total"] - inv["paid"]),
            "account_balance": r2(closing)}


def purchase_detail(db, purchase_id):
    pur = db.one("SELECT * FROM purchases WHERE id=?", (purchase_id,))
    if not pur:
        return None
    items = db.query("SELECT pi.*, p.name AS product_name FROM purchase_items pi "
                     "JOIN products p ON p.id=pi.product_id WHERE pi.purchase_id=? ORDER BY pi.id",
                     (purchase_id,))
    return {"purchase": pur, "items": items, "party": db.one("SELECT * FROM parties WHERE id=?", (pur["party_id"],)),
            "company": db.one("SELECT * FROM company WHERE id=1"),
            "balance_due": r2(pur["total"] - pur["paid"])}


def voucher_detail(db, voucher_no):
    v = db.one("SELECT * FROM vouchers WHERE no=?", (voucher_no,))
    if not v:
        return None
    return {"voucher": v, "party": db.one("SELECT * FROM parties WHERE id=?", (v["party_id"],)),
            "company": db.one("SELECT * FROM company WHERE id=1")}


# ---------------- phone-shop helpers ----------------
def imei_lookup(db, text, limit=200):
    """Find a phone by (part of) IMEI 1 or IMEI 2: where it was bought from and who it was sold to."""
    text = (text or "").strip()
    if len(text) < 3:
        return []
    like = f"%{text}%"
    return db.query(
        "SELECT s.id, s.serial, s.imei2, s.status, p.name AS product, pu.no AS purchase_no, pu.date AS purchase_date, "
        "sup.name AS supplier, i.no AS invoice_no, i.date AS invoice_date, cu.name AS customer, cu.phone AS cphone, "
        "(SELECT ii.price - ii.discount FROM invoice_items ii WHERE ii.invoice_id=s.invoice_id "
        "AND ii.serial=s.serial LIMIT 1) AS sold_price, "
        "(SELECT ii.warranty_months FROM invoice_items ii WHERE ii.invoice_id=s.invoice_id "
        "AND ii.serial=s.serial LIMIT 1) AS warranty_months "
        "FROM serials s JOIN products p ON p.id=s.product_id "
        "LEFT JOIN purchases pu ON pu.id=s.purchase_id LEFT JOIN parties sup ON sup.id=pu.party_id "
        "LEFT JOIN invoices i ON i.id=s.invoice_id LEFT JOIN parties cu ON cu.id=i.party_id "
        "WHERE s.serial LIKE ? OR s.imei2 LIKE ? ORDER BY s.id DESC LIMIT ?", (like, like, limit))


def daily_closing(db, date_from, date_to):
    """One row per day: invoices, sales, money in, money out, expenses and net cash."""
    a, b = date_from + _START, date_to + _END
    days = {}

    def day(d):
        return days.setdefault(d[:10], {"invoices": 0, "sales": 0.0, "cash_in": 0.0, "cash_out": 0.0,
                                        "expenses": 0.0})
    for r in db.query("SELECT substr(date,1,10) d, COUNT(*) n, SUM(total) t FROM invoices "
                      "WHERE status='active' AND date BETWEEN ? AND ? GROUP BY d", (a, b)):
        x = day(r["d"])
        x["invoices"], x["sales"] = r["n"], r2(r["t"])
    for r in db.query("SELECT substr(date,1,10) d, direction, SUM(amount) t FROM cash_book "
                      "WHERE date BETWEEN ? AND ? GROUP BY d, direction", (a, b)):
        day(r["d"])["cash_in" if r["direction"] == "in" else "cash_out"] = r2(r["t"])
    for r in db.query("SELECT substr(date,1,10) d, SUM(amount) t FROM expenses WHERE date BETWEEN ? AND ? GROUP BY d",
                      (a, b)):
        day(r["d"])["expenses"] = r2(r["t"])
    rows = [{"date": d, **v, "net": r2(v["cash_in"] - v["cash_out"])} for d, v in sorted(days.items())]
    return {"rows": rows, "opening": cash_book(db, date_from, date_to)["opening"],
            "closing": cash_book(db, date_from, date_to)["closing"]}


def dashboard(db, today=None):
    """Numbers for the home page cards."""
    from datetime import date as _d
    today = today or _d.today().isoformat()
    a, b = today + _START, today + _END
    sales = db.scalar("SELECT COALESCE(SUM(total),0) FROM invoices WHERE status='active' AND date BETWEEN ? AND ?",
                      (a, b))
    n = db.scalar("SELECT COUNT(*) FROM invoices WHERE status='active' AND date BETWEEN ? AND ?", (a, b))
    stock = stock_position(db)["rows"]
    return {"today_sales": r2(sales), "today_invoices": n, "cash": cash_in_hand(db),
            "receivable": all_balances(db, "customer")["total"],
            "low_stock": sum(1 for r in stock if r["low"]),
            "phones_in_stock": db.scalar("SELECT COUNT(*) FROM serials WHERE status='in_stock'"),
            "qist_overdue": db.scalar(
                "SELECT COUNT(*) FROM installments ins JOIN installment_plans p ON p.id=ins.plan_id "
                "WHERE p.status='active' AND ins.amount-ins.paid>0.004 AND ins.due_date < ?", (today,))}


# ---------------- dashboard graphs and lists ----------------
def _buckets(period, today):
    """[(from_date, to_date, label)] oldest first, ending with the period that contains `today`."""
    import calendar
    from datetime import timedelta
    if period == "daily":                                   # last 14 days
        days = [today - timedelta(days=i) for i in range(13, -1, -1)]
        return [(d, d, d.strftime("%d %b")) for d in days]
    if period == "weekly":                                  # last 12 weeks (Monday to Sunday)
        start = today - timedelta(days=today.weekday())
        weeks = [start - timedelta(days=7 * k) for k in range(11, -1, -1)]
        return [(s, s + timedelta(days=6), s.strftime("%d %b")) for s in weeks]
    if period == "monthly":                                 # last 12 months
        out = []
        for k in range(11, -1, -1):
            m0 = today.year * 12 + today.month - 1 - k
            y, m = m0 // 12, m0 % 12 + 1
            out.append((today.replace(year=y, month=m, day=1),
                        today.replace(year=y, month=m, day=calendar.monthrange(y, m)[1]),
                        today.replace(year=y, month=m, day=1).strftime("%b %y")))
        return out
    if period == "yearly":                                  # last 5 years
        return [(today.replace(year=y, month=1, day=1), today.replace(year=y, month=12, day=31), str(y))
                for y in range(today.year - 4, today.year + 1)]
    raise ValueError("period must be daily, weekly, monthly or yearly")


def dashboard_series(db, period="daily", today=None):
    """Sales (after returns) and net profit/loss for each bucket of the period, for the home-page graphs."""
    from datetime import date as _d
    today = today or _d.today()
    labels, sales, profit = [], [], []
    for a, b, label in _buckets(period, today):
        p = profit_loss(db, a.isoformat(), b.isoformat())
        labels.append(label)
        sales.append(p["net_sales"])
        profit.append(p["net_profit"])
    return {"labels": labels, "sales": sales, "profit": profit,
            "total_sales": r2(sum(sales)), "total_profit": r2(sum(profit))}


def dashboard_lists(db):
    recent = db.query("SELECT i.no, i.date, i.total, p.name AS customer FROM invoices i "
                      "JOIN parties p ON p.id=i.party_id WHERE i.status='active' ORDER BY i.id DESC LIMIT 6")
    low = sorted((r for r in stock_position(db)["rows"] if r["low"]), key=lambda r: r["qty"])[:6]
    debtors = sorted(all_balances(db, "customer")["rows"], key=lambda r: -r["balance"])[:5]
    due = db.query("SELECT DISTINCT ins.due_date FROM installments ins JOIN installment_plans p ON p.id=ins.plan_id "
                   "WHERE p.status='active' AND ins.amount-ins.paid>0.004 ORDER BY ins.due_date LIMIT 400")
    return {"recent": recent, "low_stock": low, "debtors": debtors, "due_dates": [r["due_date"] for r in due]}


# ---------------- dashboard graphs ----------------
def _bucket_start(d, kind):
    from datetime import timedelta
    if kind == "week":
        return d - timedelta(days=d.weekday())          # weeks start on Monday
    if kind == "month":
        return d.replace(day=1)
    if kind == "year":
        return d.replace(month=1, day=1)
    return d


def _next_bucket(d, kind):
    from datetime import timedelta
    if kind == "day":
        return d + timedelta(days=1)
    if kind == "week":
        return d + timedelta(days=7)
    if kind == "month":
        return d.replace(year=d.year + (d.month == 12), month=d.month % 12 + 1)
    return d.replace(year=d.year + 1)


def _prev_bucket(d, kind):
    from datetime import timedelta
    if kind == "day":
        return d - timedelta(days=1)
    if kind == "week":
        return d - timedelta(days=7)
    if kind == "month":
        return (d - timedelta(days=1)).replace(day=1)
    return d.replace(year=d.year - 1)


_LAST = {"day": 14, "week": 8, "month": 12, "year": 5}


def _label(d, kind):
    return {"day": f"{d.day}/{d.month}", "week": f"{d.day}/{d.month}", "month": d.strftime("%b %y"),
            "year": str(d.year)}[kind]


def bucket_starts(kind, today=None, count=None):
    from datetime import date
    today = today or date.today()
    cur, out = _bucket_start(today, kind), []
    for _ in range(count or _LAST[kind]):
        out.append(cur)
        cur = _prev_bucket(cur, kind)
    return out[::-1]


def sales_series(db, kind="day", today=None):
    """[(label, sales)] for the last 14 days / 8 weeks / 12 months / 5 years (empty periods are 0)."""
    from datetime import date
    today = today or date.today()
    starts = bucket_starts(kind, today)
    rows = db.query("SELECT date, total FROM invoices WHERE status='active' AND date >= ?",
                    (starts[0].isoformat() + _START,))
    totals = {s: 0.0 for s in starts}
    for r in rows:
        s = _bucket_start(date.fromisoformat(r["date"][:10]), kind)
        if s in totals:
            totals[s] += r["total"]
    return [(_label(s, kind), r2(totals[s])) for s in starts]


def profit_series(db, today=None, months=12):
    """[(label, net profit or loss)] per month for the last `months` months."""
    from datetime import date
    today = today or date.today()
    out = []
    for s in bucket_starts("month", today, months):
        end = _next_bucket(s, "month")
        last = date.fromordinal(end.toordinal() - 1)
        out.append((_label(s, "month"), profit_loss(db, s.isoformat(), last.isoformat())["net_profit"]))
    return out


def dashboard_extras(db, today=None):
    """More numbers for the dashboard: this month/year, top products, low stock, qist due, open repairs."""
    from datetime import date
    today = today or date.today()
    m0, y0 = today.replace(day=1), today.replace(month=1, day=1)
    iso = today.isoformat()
    month_sales = db.scalar("SELECT COALESCE(SUM(total),0) FROM invoices WHERE status='active' AND date >= ?",
                            (m0.isoformat() + _START,))
    month = profit_loss(db, m0.isoformat(), iso)["net_profit"]
    year = profit_loss(db, y0.isoformat(), iso)["net_profit"]
    top = db.query("SELECT p.name, SUM(ii.qty) AS qty, SUM(ii.qty*ii.price-ii.discount) AS amount "
                   "FROM invoice_items ii JOIN invoices i ON i.id=ii.invoice_id JOIN products p ON p.id=ii.product_id "
                   "WHERE i.status='active' AND i.date >= ? GROUP BY p.id ORDER BY amount DESC LIMIT 5",
                   (m0.isoformat() + _START,))
    low = [r for r in stock_position(db)["rows"] if r["low"]][:8]
    from .installments import due_list
    qist = [r for r in due_list(db, iso) if r["days_late"] >= -3][:6]
    return {"month_sales": r2(month_sales), "month_profit": month, "year_profit": year, "top_products": top,
            "low_items": low, "qist_due": qist,
            "open_repairs": db.scalar("SELECT COUNT(*) FROM repairs WHERE status IN "
                                      "('received','in_progress','ready')")}


def dashboard_overview(db, today=None):
    """Read-only numbers for the Dashboard cards (this month): sales, purchases, expenses, net profit,
    what customers owe, what is owed to suppliers and the stock on the shelf. Nothing is written."""
    from datetime import date
    today = today or date.today()
    m0 = today.replace(day=1).isoformat() + _START
    sales = db.scalar("SELECT COALESCE(SUM(total),0) FROM invoices WHERE status='active' AND date >= ?", (m0,))
    purchases = db.scalar("SELECT COALESCE(SUM(total),0) FROM purchases WHERE status='active' AND date >= ?", (m0,))
    pl = profit_loss(db, today.replace(day=1).isoformat(), today.isoformat())
    stock = stock_position(db)
    return {"month_sales": r2(sales), "month_purchases": r2(purchases), "month_expenses": pl["expenses"],
            "month_profit": pl["net_profit"],
            "receivable": all_balances(db, "customer")["total"], "payable": all_balances(db, "supplier")["total"],
            "stock_units": sum(max(r["qty"], 0) for r in stock["rows"]), "stock_value": stock["total_value"]}


def recent_transactions(db, limit=8, include_purchases=True):
    """The latest bills (and purchases) for the Dashboard list."""
    sale = ("SELECT i.date AS date, 'Sale' AS kind, i.no AS no, p.name AS party, i.total AS amount "
            "FROM invoices i JOIN parties p ON p.id=i.party_id WHERE i.status='active'")
    buy = ("SELECT u.date, 'Purchase', u.no, p.name, u.total FROM purchases u JOIN parties p ON p.id=u.party_id "
           "WHERE u.status='active'")
    sql = sale + (" UNION ALL " + buy if include_purchases else "") + " ORDER BY date DESC LIMIT ?"
    return db.query(sql, (limit,))
