"""Report builders: turn service data into a plain table (headers/rows/summary).

A report is a dict:
  title, subtitle, headers, rows (list of lists of display strings), numeric (set of right-aligned
  column indexes), bold_rows (set of row indexes), summary [(label, value)], key_col (optional).
The same structure feeds the on-screen table, CSV, Excel and PDF, so they always agree.
"""
from ..services import reports as R


def money(x) -> str:
    return f"{x:,.2f}"


def _new(title, subtitle, headers, numeric=()):
    return {"title": title, "subtitle": subtitle, "headers": headers, "rows": [], "numeric": set(numeric),
            "bold_rows": set(), "summary": []}


def _desc(r):
    labels = {"invoice": "Sale", "purchase": "Purchase", "receipt": "Cash received", "payment": "Paid to supplier",
              "customer_payment": "Paid to customer", "expense": "Expense", "sale_return": "Sale return",
              "purchase_return": "Purchase return"}
    base = labels.get(r["ref_type"], r["ref_type"])
    return f"{base}: {r['note']}" if r.get("note") else base


def cash_book_report(db, date_from, date_to):
    cb = R.cash_book(db, date_from, date_to)
    rep = _new("Cash Book", f"{date_from}  to  {date_to}",
               ["Date", "Description", "Party", "Cash In", "Cash Out", "Balance"], (3, 4, 5))
    bal = cb["opening"]
    rep["rows"].append(["", "Opening balance", "", "", "", money(bal)])
    rep["bold_rows"].add(0)
    for r in cb["rows"]:
        bal += r["amount"] if r["direction"] == "in" else -r["amount"]
        rep["rows"].append([r["date"][:16], _desc(r), r["party_name"] or "",
                            money(r["amount"]) if r["direction"] == "in" else "",
                            money(r["amount"]) if r["direction"] == "out" else "", money(bal)])
    rep["rows"].append(["", "Closing balance", "", money(cb["total_in"]), money(cb["total_out"]),
                        money(cb["closing"])])
    rep["bold_rows"].add(len(rep["rows"]) - 1)
    rep["summary"] = [("Opening", money(cb["opening"])), ("Total in", money(cb["total_in"])),
                      ("Total out", money(cb["total_out"])), ("Closing", money(cb["closing"]))]
    return rep


def balance_sheet_report(db, as_of=None):
    b = R.balance_sheet(db)
    rep = _new("Balance Sheet", f"As of {as_of or 'today'}", ["Particulars", "Amount"], (1,))
    rows = [("ASSETS", ""), ("Cash in hand", money(b["cash"])), ("Stock value (at cost)", money(b["stock_value"])),
            ("Receivables (customers owe us)", money(b["receivables"])), ("TOTAL ASSETS", money(b["total_assets"])),
            ("", ""), ("LIABILITIES", ""), ("Payables (we owe suppliers)", money(b["payables"])),
            ("TOTAL LIABILITIES", money(b["total_liabilities"])), ("", ""),
            ("EQUITY / NET WORTH (Assets - Liabilities)", money(b["equity"]))]
    for i, r in enumerate(rows):
        rep["rows"].append(list(r))
        if r[0].isupper() and r[0]:
            rep["bold_rows"].add(i)
    rep["summary"] = [("Total assets", money(b["total_assets"])), ("Total liabilities", money(b["total_liabilities"])),
                      ("Equity", money(b["equity"]))]
    return rep


def vouchers_report(db, date_from, date_to):
    rep = _new("Vouchers", f"{date_from}  to  {date_to}", ["Voucher No", "Date", "Type", "Party", "Amount", "Note"], (4,))
    rows = db.query("SELECT v.*, p.name AS party_name FROM vouchers v LEFT JOIN parties p ON p.id=v.party_id "
                    "WHERE v.date BETWEEN ? AND ? ORDER BY v.date, v.id",
                    (date_from + " 00:00:00", date_to + " 23:59:59"))
    rec = pay = 0.0
    for v in rows:
        rep["rows"].append([v["no"], v["date"][:16], "Receipt" if v["kind"] == "receipt" else "Payment",
                            v["party_name"] or "", money(v["amount"]), v["note"] or ""])
        if v["kind"] == "receipt":
            rec += v["amount"]
        else:
            pay += v["amount"]
    rep["summary"] = [("Receipts", money(rec)), ("Payments", money(pay))]
    return rep


# ======================= more reports =======================
_LEDGER_LABELS = {"invoice": "Sale", "purchase": "Purchase", "receipt": "Cash received", "payment": "Payment",
                  "customer_payment": "Paid to customer", "sale_return": "Sale return",
                  "purchase_return": "Purchase return",
                  "adjustment": "Balance cleared"}


def _ledger_desc(r):
    base = _LEDGER_LABELS.get(r["ref_type"], r["ref_type"])
    return f"{base}: {r['note']}" if r.get("note") else base


def _empty(title, message):
    rep = _new(title, "", [message])
    return rep


def customer_transactions_report(db, date_from, date_to, party_id=None):
    if not party_id:
        return _empty("Customer Transactions", "Select a customer above")
    led = R.customer_ledger(db, party_id, date_from, date_to)
    party = led["party"]
    is_cust = party["kind"] == "customer"
    rep = _new("Customer Transactions" if is_cust else "Supplier Transactions",
               f"{party['name']} (ID {party['id']})   {date_from}  to  {date_to}",
               ["Date", "Description", "Debit", "Credit", "Balance"], (2, 3, 4))
    opening, closing = led["period_opening"], led["period_closing"]
    rep["rows"].append(["", "Balance before this period", "", "", money(opening)])
    rep["bold_rows"].add(0)
    for r in led["rows"]:
        rep["rows"].append([r["date"][:16], _ledger_desc(r), money(r["debit"]) if r["debit"] else "",
                            money(r["credit"]) if r["credit"] else "", money(r["balance"])])
    rep["rows"].append(["", "Closing balance", money(sum(r["debit"] for r in led["rows"])),
                        money(sum(r["credit"] for r in led["rows"])), money(closing)])
    rep["bold_rows"].add(len(rep["rows"]) - 1)
    rep["summary"] = [("Closing balance", money(closing)),
                      ("Meaning", "customer owes us" if is_cust else "we owe supplier")]
    return rep


def cash_received_report(db, date_from, date_to):
    rows = db.query("SELECT c.*, p.name AS party_name FROM cash_book c LEFT JOIN parties p ON p.id=c.party_id "
                    "WHERE c.direction='in' AND c.ref_type IN ('invoice','receipt') AND c.date BETWEEN ? AND ? "
                    "ORDER BY c.date, c.id", (date_from + " 00:00:00", date_to + " 23:59:59"))
    rep = _new("Cash Received", f"{date_from}  to  {date_to}", ["Date", "Customer", "Description", "Amount"], (3,))
    total = 0.0
    for r in rows:
        rep["rows"].append([r["date"][:16], r["party_name"] or "", _desc(r), money(r["amount"])])
        total += r["amount"]
    rep["rows"].append(["", "TOTAL", "", money(total)])
    rep["bold_rows"].add(len(rep["rows"]) - 1)
    rep["summary"] = [("Total received", money(total))]
    return rep


def profit_loss_report(db, date_from, date_to):
    p = R.profit_loss(db, date_from, date_to)
    rep = _new("Profit & Loss", f"{date_from}  to  {date_to}", ["Particulars", "Amount"], (1,))
    rows = [("Sales", p["sales"]), ("Less: sale returns", p["sale_returns"]), ("NET SALES", p["net_sales"]),
            ("Cost of goods sold", p["cost_of_goods"]), ("GROSS PROFIT", p["gross_profit"]),
            ("Expenses", p["expenses"]), ("NET PROFIT / (LOSS)", p["net_profit"])]
    for i, (a, b) in enumerate(rows):
        rep["rows"].append([a, money(b)])
        if a.isupper() or a.startswith("NET"):
            rep["bold_rows"].add(i)
    rep["summary"] = [("Net profit" if p["net_profit"] >= 0 else "Net loss", money(abs(p["net_profit"])))]
    return rep


def invoice_wise_report(db, date_from, date_to):
    rows = R.invoice_wise_summary(db, date_from, date_to)
    rep = _new("Invoice Wise Sale Summary", f"{date_from}  to  {date_to}",
               ["Invoice", "Date", "Customer", "Total", "Paid", "Balance", "Profit"], (3, 4, 5, 6))
    tt = tp = tb = tf = 0.0
    for r in rows:
        rep["rows"].append([r["no"], r["date"][:16], r["customer"], money(r["total"]), money(r["paid"]),
                            money(r["balance"]), money(r["profit"])])
        tt, tp, tb, tf = tt + r["total"], tp + r["paid"], tb + r["balance"], tf + r["profit"]
    rep["rows"].append(["TOTAL", "", f"{len(rows)} invoices", money(tt), money(tp), money(tb), money(tf)])
    rep["bold_rows"].add(len(rep["rows"]) - 1)
    rep["summary"] = [("Sales", money(tt)), ("Received", money(tp)), ("Profit", money(tf))]
    return rep


def stock_position_report(db):
    sp = R.stock_position(db)
    rep = _new("Stock Position", "Quantity and value at average cost",
               ["ID", "Product", "Category", "Unit", "Quantity", "Avg Cost", "Value", "Sale Price", "Status"],
               (4, 5, 6, 7))
    low = 0
    for r in sp["rows"]:
        rep["rows"].append([r["id"], r["name"], r["category"] or "", r["unit"] or "", f"{r['qty']:g}",
                            money(r["avg_cost"]), money(r["value"]), money(r["sale_price"]),
                            "LOW STOCK" if r["low"] else ""])
        low += r["low"]
    rep["rows"].append(["", "TOTAL STOCK VALUE", "", "", "", "", money(sp["total_value"]), "", ""])
    rep["bold_rows"].add(len(rep["rows"]) - 1)
    rep["summary"] = [("Products", str(len(sp["rows"]))), ("Low stock", str(low)),
                      ("Stock value", money(sp["total_value"]))]
    rep["low_rows"] = {i for i, r in enumerate(sp["rows"]) if r["low"]}   # highlighted on screen
    return rep


def product_ledger_report(db, date_from, date_to, product_id=None):
    if not product_id:
        return _empty("Products Ledger", "Select a product above")
    pl = R.product_ledger(db, product_id, date_from, date_to)
    p = pl["product"]
    rep = _new("Products Ledger", f"{p['name']} (ID {p['id']})   {date_from}  to  {date_to}",
               ["Date", "Description", "Qty In", "Qty Out", "Balance"], (2, 3, 4))
    labels = {"invoice": "Sale", "purchase": "Purchase", "sale_return": "Sale return",
              "purchase_return": "Purchase return"}
    first = pl["rows"][0] if pl["rows"] else None
    opening = (first["balance"] - first["qty"]) if first else pl["closing"]
    rep["rows"].append(["", "Balance before this period", "", "", f"{opening:g}"])
    rep["bold_rows"].add(0)
    for m in pl["rows"]:
        rep["rows"].append([m["date"][:16], labels.get(m["ref_type"], m["ref_type"]),
                            f"{m['qty']:g}" if m["qty"] > 0 else "", f"{-m['qty']:g}" if m["qty"] < 0 else "",
                            f"{m['balance']:g}"])
    rep["rows"].append(["", "Closing stock", "", "", f"{pl['rows'][-1]['balance'] if pl['rows'] else opening:g}"])
    rep["bold_rows"].add(len(rep["rows"]) - 1)
    rep["summary"] = [("Current stock", f"{pl['closing']:g}")]
    return rep


def all_customer_balance_report(db):
    b = R.all_balances(db, "customer")
    rep = _new("All Customer Balance", "Customers who owe us", ["ID", "Customer", "Phone", "Balance"], (3,))
    for r in b["rows"]:
        rep["rows"].append([r["id"], r["name"], r["phone"] or "", money(r["balance"])])
    rep["rows"].append(["", "TOTAL RECEIVABLE", "", money(b["total"])])
    rep["bold_rows"].add(len(rep["rows"]) - 1)
    rep["summary"] = [("Customers", str(len(b["rows"]))), ("Total", money(b["total"]))]
    return rep


def outstanding_report(db):
    """Outstanding / Baqayajat: ONLY customers who still owe us money. Suppliers, wholesalers and
    dealers are not listed (purchases are always saved as fully paid)."""
    b = R.all_balances(db, "customer")
    rep = _new("Outstanding / Baqayajat", "Customers who have to pay", ["ID", "Customer", "Phone", "Balance"], (3,))
    for r in b["rows"]:
        rep["rows"].append([r["id"], r["name"], r["phone"] or "", money(r["balance"])])
    rep["rows"].append(["", "TOTAL TO RECEIVE", "", money(b["total"])])
    rep["bold_rows"].add(len(rep["rows"]) - 1)
    rep["summary"] = [("Customers", str(len(b["rows"]))), ("Total to receive", money(b["total"]))]
    return rep


def sale_summary_report(db, date_from, date_to):
    rep = _new("Sale Summary", f"{date_from}  to  {date_to}", ["Period", "Invoices", "Sales", "Received"], (1, 2, 3))
    for title, group in (("DAILY", "day"), ("MONTHLY", "month")):
        s = R.sale_summary(db, date_from, date_to, group)
        rep["rows"].append([title, "", "", ""])
        rep["bold_rows"].add(len(rep["rows"]) - 1)
        for r in s["rows"]:
            rep["rows"].append([r["period"], r["invoices"], money(r["sales"]), money(r["received"])])
        rep["rows"].append(["Total", sum(r["invoices"] for r in s["rows"]), money(s["total"]),
                            money(sum(r["received"] for r in s["rows"]))])
        rep["bold_rows"].add(len(rep["rows"]) - 1)
        if group == "day":
            rep["summary"] = [("Total sales", money(s["total"]))]
    return rep


def products_report(db):
    rows = R.stock_position(db)["rows"]
    tags = {r["id"]: r["tags"] or "" for r in db.query("SELECT id, tags FROM products")}
    rep = _new("Products", "All active products",
               ["ID", "Product", "Category", "Tags", "Unit", "Avg Cost", "Sale Price", "Stock"], (5, 6, 7))
    for r in rows:
        rep["rows"].append([r["id"], r["name"], r["category"] or "", tags.get(r["id"], ""), r["unit"] or "",
                            money(r["avg_cost"]), money(r["sale_price"]), f"{r['qty']:g}"])
    rep["summary"] = [("Products", str(len(rows)))]
    return rep


def invoice_list_report(db, date_from, date_to):
    """Used by the Invoice Print screen: first column is the invoice number."""
    rows = db.query("SELECT i.*, p.name AS customer FROM invoices i JOIN parties p ON p.id=i.party_id "
                    "WHERE i.date BETWEEN ? AND ? ORDER BY i.date DESC, i.id DESC",
                    (date_from + " 00:00:00", date_to + " 23:59:59"))
    rep = _new("Invoice Print", f"{date_from}  to  {date_to}",
               ["Invoice", "Date", "Customer", "Total", "Paid", "Balance", "Status"], (3, 4, 5))
    for r in rows:
        rep["rows"].append([r["no"], r["date"][:16], r["customer"], money(r["total"]), money(r["paid"]),
                            money(r["total"] - r["paid"]), "Cancelled" if r["status"] == "cancelled" else "Active"])
    rep["summary"] = [("Invoices", str(len(rows)))]
    return rep
