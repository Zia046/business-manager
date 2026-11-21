"""Business figures for the Android Companion app: stock, mobiles in hand, sales, purchases, money, activity.

Everything is read from the shop's own records with the same functions the Windows screens use
(stock_position, profit_loss, cash_in_hand, all_balances, phones.in_stock), so the phone shows the same
numbers as the PC. Nothing is estimated and nothing is written."""
from datetime import date

from . import phones
from .common import r2
from .reports import _END, _START, all_balances, cash_in_hand, profit_loss, sales_series, stock_position

MOBILE_LIST_MAX = 1000
_ACTIVITY = ("Product added", "Product edited", "Product deleted", "Phone in stock edited", "Phone removed from stock",
             "2nd hand phone purchased", "Purchase return", "Sale return", "Sale invoice cancelled")
_MOVE_LABELS = {"invoice": "Sale", "purchase": "Purchase", "sale_return": "Sale return",
                "purchase_return": "Purchase return", "repair": "Repair", "phone_edit": "Phone corrected",
                "phone_removed": "Phone removed"}


def stock(db) -> dict:
    rows = stock_position(db)["rows"]
    have = [r for r in rows if r["qty"] > 0]
    cats = {}
    for r in have:
        c = cats.setdefault(r["category"] or "Other", {"category": r["category"] or "Other", "items": 0, "qty": 0.0,
                                                       "purchase_value": 0.0, "sale_value": 0.0})
        c["items"] += 1
        c["qty"] += r["qty"]
        c["purchase_value"] += r["value"]
        c["sale_value"] += r["qty"] * r["sale_price"]
    for c in cats.values():
        c["qty"], c["purchase_value"], c["sale_value"] = r2(c["qty"]), r2(c["purchase_value"]), r2(c["sale_value"])
    others = [r for r in rows if not r["is_phone"]]              # low / finished: never mobile phones
    low = [r for r in others if r["low"] and r["qty"] > 0]
    out = [r for r in others if r["qty"] <= 0]
    return {"items": len(have), "quantity": r2(sum(r["qty"] for r in have)),
            "purchase_value": r2(sum(r["value"] for r in have)),
            "sale_value": r2(sum(r["qty"] * r["sale_price"] for r in have)),
            "products_total": len(rows), "available_items": len(have),
            "low_count": len(low), "out_count": len(out),
            "low_items": [{"name": r["name"], "category": r["category"] or "", "qty": r2(r["qty"]),
                           "level": r2(r["low_stock_level"])} for r in sorted(low, key=lambda r: r["qty"])[:50]],
            "categories": sorted(cats.values(), key=lambda c: -c["purchase_value"])}


def mobiles(db) -> dict:
    rows = phones.in_stock(db)                                   # only phones that are in the shop now
    brands, models = {}, {}
    for r in rows:
        b = r["brand"] or "Other"
        brands[b] = brands.get(b, 0) + 1
        key = (b, r["name"])
        models[key] = models.get(key, 0) + 1
    return {"total": len(rows),
            "purchase_value": r2(sum(r["purchase_price"] for r in rows)),
            "sale_value": r2(sum(r["sale_price"] for r in rows)),
            "brands": [{"brand": k, "qty": v} for k, v in sorted(brands.items(), key=lambda kv: (-kv[1], kv[0]))],
            "models": [{"brand": k[0], "model": k[1], "qty": v}
                       for k, v in sorted(models.items(), key=lambda kv: (-kv[1], kv[0]))],
            "phones": [{"id": f"S-{r['serial_id']}", "brand": r["brand"], "model": r["name"],
                        "type": phones.TYPES.get(r["mobile_type"], ""), "ram_gb": r["ram_gb"],
                        "storage_gb": r["storage_gb"], "condition": phones.CONDITIONS[r["condition"]],
                        "imei1": r["imei1"], "imei2": r["imei2"] or "", "purchase_price": r["purchase_price"],
                        "sale_price": r["sale_price"]} for r in rows[:MOBILE_LIST_MAX]]}


def _sum(db, table, a, b):
    return r2(db.scalar(f"SELECT COALESCE(SUM(total),0) FROM {table} WHERE status='active' AND date BETWEEN ? AND ?",
                        (a, b)))


def _count(db, table, a, b):
    return db.scalar(f"SELECT COUNT(*) FROM {table} WHERE status='active' AND date BETWEEN ? AND ?", (a, b))


def sales(db, today: date) -> dict:
    d, m0 = today.isoformat(), today.replace(day=1).isoformat()
    todays = db.query("SELECT i.no, i.date, i.total, i.paid, p.name AS customer FROM invoices i JOIN parties p "
                      "ON p.id=i.party_id WHERE i.status='active' AND i.date BETWEEN ? AND ? ORDER BY i.date DESC, "
                      "i.id DESC LIMIT 100", (d + _START, d + _END))
    return {"today_total": _sum(db, "invoices", d + _START, d + _END), "today_count": _count(db, "invoices", d + _START, d + _END),
            "month_total": _sum(db, "invoices", m0 + _START, d + _END), "month_count": _count(db, "invoices", m0 + _START, d + _END),
            "all_count": db.scalar("SELECT COUNT(*) FROM invoices WHERE status='active'"),
            "all_total": r2(db.scalar("SELECT COALESCE(SUM(total),0) FROM invoices WHERE status='active'")),
            "today_list": [{"no": r["no"], "time": r["date"][11:16], "customer": r["customer"], "total": r2(r["total"]),
                            "paid": r2(r["paid"])} for r in todays],
            "monthly": [{"month": label, "total": total} for label, total in sales_series(db, "month", today)]}


def purchases(db, today: date) -> dict:
    d, m0 = today.isoformat(), today.replace(day=1).isoformat()
    recent = db.query("SELECT u.no, u.date, u.total, p.name AS supplier FROM purchases u JOIN parties p "
                      "ON p.id=u.party_id WHERE u.status='active' ORDER BY u.date DESC, u.id DESC LIMIT 15")
    return {"today_total": _sum(db, "purchases", d + _START, d + _END), "today_count": _count(db, "purchases", d + _START, d + _END),
            "month_total": _sum(db, "purchases", m0 + _START, d + _END),
            "all_total": r2(db.scalar("SELECT COALESCE(SUM(total),0) FROM purchases WHERE status='active'")),
            "all_count": db.scalar("SELECT COUNT(*) FROM purchases WHERE status='active'"),
            "recent": [{"no": r["no"], "date": r["date"][:16], "supplier": r["supplier"], "total": r2(r["total"])}
                       for r in recent]}


def finance(db, today: date) -> dict:
    d = today.isoformat()
    return {"receivables": all_balances(db, "customer")["total"], "payables": all_balances(db, "supplier")["total"],
            "today_profit": profit_loss(db, d, d)["net_profit"],
            "month_profit": profit_loss(db, today.replace(day=1).isoformat(), d)["net_profit"],
            "cash_in_hand": cash_in_hand(db)}


def activity(db) -> dict:
    sales_ = db.query("SELECT i.no, i.date, i.total, p.name FROM invoices i JOIN parties p ON p.id=i.party_id "
                      "WHERE i.status='active' ORDER BY i.date DESC, i.id DESC LIMIT 10")
    buys = db.query("SELECT u.no, u.date, u.total, p.name FROM purchases u JOIN parties p ON p.id=u.party_id "
                    "WHERE u.status='active' ORDER BY u.date DESC, u.id DESC LIMIT 10")
    added = db.query("SELECT date, detail FROM audit_log WHERE action='Product added' ORDER BY id DESC LIMIT 10")
    moves = db.query("SELECT m.id, m.date, m.qty, m.ref_type, p.name FROM stock_moves m JOIN products p "
                     "ON p.id=m.product_id ORDER BY m.date DESC, m.id DESC LIMIT 15")
    marks = ",".join("?" * len(_ACTIVITY))
    log = db.query(f"SELECT date, action, detail FROM audit_log WHERE action IN ({marks}) ORDER BY id DESC LIMIT 15",
                   _ACTIVITY)
    return {"sales": [{"date": r["date"][:16], "no": r["no"], "name": r["name"], "amount": r2(r["total"])} for r in sales_],
            "purchases": [{"date": r["date"][:16], "no": r["no"], "name": r["name"], "amount": r2(r["total"])}
                          for r in buys],
            "new_products": [{"date": r["date"][:16], "text": r["detail"]} for r in added],
            "stock_updates": [{"date": r["date"][:16], "product": r["name"], "qty": r2(r["qty"]),
                               "kind": _MOVE_LABELS.get(r["ref_type"], r["ref_type"].replace("_", " ").title())}
                              for r in moves],
            "changes": [{"date": r["date"][:16], "action": r["action"], "text": (r["detail"] or "")[:160]} for r in log]}


def overview(db, today: date | None = None) -> dict:
    today = today or date.today()
    return {"stock": stock(db), "mobiles": mobiles(db), "sales": sales(db, today), "purchases": purchases(db, today),
            "finance": finance(db, today), "activity": activity(db)}
