"""WhatsApp reminder messages (the program only builds the text and the link; the person presses Send)."""
import re
from urllib.parse import quote

from .common import r2


def normalize_phone(phone, country="92") -> str:
    """'0347-5093446' -> '923475093446' (digits only, with country code). '' if there is no number."""
    digits = re.sub(r"\D", "", phone or "")
    if digits.startswith("00"):
        digits = digits[2:]
    if not digits:
        return ""
    if digits.startswith("0"):
        digits = country + digits[1:]
    elif len(digits) == 10 and digits.startswith("3"):
        digits = country + digits
    return digits


def whatsapp_url(phone, text) -> str:
    return f"https://wa.me/{normalize_phone(phone)}?text={quote(text)}"


# ---- SMS reminders sent by the phone app (the PC only prepares the list; the phone sends from its own SIM) ----
SMS_PLACEHOLDER = "xxxxxx"          # replaced by the customer's balance
DEFAULT_SMS_TEMPLATE = """Burhan Nexus
📞 0347-5093446
محترم صارف،
امید ہے آپ خیریت سے ہوں گے۔
آپ کے لیجر کے مطابق ( xxxxxx) روپے کی رقم تاحال واجب الادا ہے۔
براہِ کرم ہماری درخواست ہے کہ ادائیگی جلد از جلد ممکن بنائیں تاکہ حسابات بروقت کلیئر ہو سکیں۔
Easypaisa ادائیگی کی تفصیل:
نام: Ziaullah
نمبر: 03139271732
آپ کے اعتماد اور تعاون کا تہہ دل سے شکریہ"""


def sms_text(template, amount) -> str:
    """The message for one customer: every 'xxxxxx' becomes his balance, e.g. 12,500."""
    return (template or DEFAULT_SMS_TEMPLATE).replace(SMS_PLACEHOLDER, f"{r2(amount):,.0f}")


def mobile_export(db, template=None) -> dict:
    """Everything the phone app needs: the customers who owe money (with a phone number) and their finished message."""
    from datetime import datetime
    from .reports import all_balances
    template = template or DEFAULT_SMS_TEMPLATE
    items, no_phone = [], 0
    for r in all_balances(db, "customer")["rows"]:
        if r["balance"] <= 0:
            continue
        phone = re.sub(r"[^\d+]", "", r["phone"] or "")
        if not phone:
            no_phone += 1
            continue
        items.append({"id": r["id"], "name": r["name"], "phone": phone, "amount": r["balance"],
                      "message": sms_text(template, r["balance"])})
    return {"app": "BusinessManagerReminders", "version": 1, "shop": _shop(db)[0],
            "created": datetime.now().strftime("%Y-%m-%d %H:%M"), "no_phone": no_phone, "items": items}


def _shop(db):
    co = db.one("SELECT name, phone FROM company WHERE id=1")
    return co["name"], co["phone"]


def balance_message(db, party_id):
    """(phone, text) asking the customer to pay what he owes."""
    from .common import customer_balance
    p = db.one("SELECT * FROM parties WHERE id=?", (party_id,))
    shop, shop_phone = _shop(db)
    bal = r2(customer_balance(db.conn, party_id))
    text = (f"Assalam o Alaikum {p['name']},\n{shop} ki taraf se yaad dehani: aap ke zimme {bal:,.0f} rupay "
            f"baqaya hain. Meherbani karke jaldi ada kar dein.\nShukriya.\n{shop}  {shop_phone}")
    return p["phone"] or "", text


def qist_message(db, party_id):
    """(phone, text) about the customer's installments that are due or late."""
    from .installments import due_list
    p = db.one("SELECT * FROM parties WHERE id=?", (party_id,))
    shop, shop_phone = _shop(db)
    due = [r for r in due_list(db) if r["party_id"] == party_id and r["days_late"] >= 0]
    if not due:
        return p["phone"] or "", ""
    total = r2(sum(r["remaining"] for r in due))
    lines = "\n".join(f"- {r['due_date']}: {r['remaining']:,.0f}" for r in due[:6])
    text = (f"Assalam o Alaikum {p['name']},\n{shop} ki taraf se yaad dehani: aap ki qist ki {total:,.0f} rupay "
            f"ki raqam ada karna baqi hai:\n{lines}\nMeherbani karke jaldi ada kar dein.\nShukriya.\n{shop}  {shop_phone}")
    return p["phone"] or "", text


def repair_ready_message(db, repair_id):
    r = db.one("SELECT * FROM repairs WHERE id=?", (repair_id,))
    shop, shop_phone = _shop(db)
    due = r2(r["charges"] - r["received"])
    extra = f" Baqaya raqam: {due:,.0f} rupay." if due > 0 else ""
    text = (f"Assalam o Alaikum {r['customer_name']},\nAap ka {r['device']} ({r['no']}) tayyar hai. Meherbani "
            f"karke le jayein.{extra}\nShukriya.\n{shop}  {shop_phone}")
    return r["phone"] or "", text
