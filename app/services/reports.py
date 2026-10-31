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
    gross = r2(net_sales - net_cogs)
    return {"sales": r2(sales), "sale_returns": r2(ret), "net_sales": net_sales,
            "cost_of_goods": net_cogs, "gross_profit": gross, "expenses": r2(exp),
            "net_profit": r2(gross - exp)}


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
