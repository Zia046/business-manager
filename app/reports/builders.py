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
