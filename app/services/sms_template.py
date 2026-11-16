"""Outstanding SMS template: one message for the whole business, edited on the PC or on the phone.

Where the customer's balance must appear the owner writes four stars: ****  (or (****)).
Every save gets the next version number; a save that was based on an older version is refused,
so an old copy on one device can never silently overwrite a newer message."""
import re

from . import settings_store
from .common import BusinessError, now, r2

PLACEHOLDER = "****"
_FOUR = r"(?<!\*)\*{4}(?!\*)"                       # exactly four stars, not part of a longer row of stars
_SLOT = re.compile(r"\(\s*" + _FOUR + r"\s*\)|" + _FOUR)
_OLD = re.compile(r"\(\s*xxxxxx\s*\)|xxxxxx")       # the placeholder of earlier versions
INSTRUCTIONS_UR = ("اپنا پیغام اپنی مرضی کے مطابق تحریر کریں۔ جہاں آپ کسٹمر کی بقایا رقم ظاہر کرنا چاہتے ہیں، "
                   "وہاں لازماً چار ستارے (****) لکھیں۔ سافٹ ویئر خود متعلقہ کسٹمر کی اصل بقایا رقم ظاہر کرے گا۔")
BUSINESS_FIELDS = ("business_name", "contact", "account_name", "easypaisa", "jazzcash", "other")
KEY_TEMPLATE, KEY_BUSINESS = "sms_template", "sms_business"


class TemplateConflict(BusinessError):
    """Someone saved a newer message in the meantime. `.current` is that newer message."""

    def __init__(self, current):
        super().__init__("The message was changed on another device. The newest message has been loaded; "
                         "make your change again and save.")
        self.current = current


# ---------- business details (separate for every installation) ----------
def business(db) -> dict:
    saved = settings_store.get(db, KEY_BUSINESS)
    if saved:
        return {k: saved.get(k, "") for k in BUSINESS_FIELDS}
    co = db.one("SELECT name, phone FROM company WHERE id=1") or {"name": "", "phone": ""}
    out = {k: "" for k in BUSINESS_FIELDS}
    out.update(business_name=co["name"] or "", contact=co["phone"] or "")
    if "burhan nexus" in out["business_name"].lower():      # the first shop's own payment details
        out.update(contact="0347-5093446", account_name="Ziaullah", easypaisa="03139271732")
    return out


def save_business(db, **values) -> dict:
    cur = business(db)
    for k in BUSINESS_FIELDS:
        if k in values:
            cur[k] = str(values[k] or "").strip()[:200]
    if not cur["business_name"]:
        raise BusinessError("Business name is required")
    settings_store.save(db, KEY_BUSINESS, cur)
    return cur


def default_text(db) -> str:
    """The standard Urdu message, filled with this business's own name, number and payment details."""
    b = business(db)
    lines = [b["business_name"]]
    if b["contact"]:
        lines.append(f"📞 {b['contact']}")
    lines += ["", "محترم صارف،", "امید ہے آپ خیریت سے ہوں گے۔", "",
              "آپ کے لیجر کے مطابق (****) روپے کی رقم تاحال واجب الادا ہے۔", "",
              "براہِ کرم ہماری درخواست ہے کہ ادائیگی جلد از جلد ممکن بنائیں تاکہ حسابات بروقت کلیئر ہو سکیں۔"]
    pay = []
    if b["easypaisa"]:
        pay += ["Easypaisa ادائیگی کی تفصیل:"] + ([f"نام: {b['account_name']}"] if b["account_name"] else []) + [
            f"نمبر: {b['easypaisa']}"]
    if b["jazzcash"]:
        pay += ["JazzCash ادائیگی کی تفصیل:"] + ([f"نام: {b['account_name']}"] if b["account_name"] else []) + [
            f"نمبر: {b['jazzcash']}"]
    if b["other"]:
        pay.append(b["other"])
    if pay:
        lines += [""] + pay
    lines += ["", "آپ کے اعتماد اور تعاون کا تہہ دل سے شکریہ۔"]
    return "\n".join(lines)


# ---------- the message ----------
def check(text) -> str:
    """The text ready to be saved, or a BusinessError that says what is wrong."""
    text = (text or "").replace("\r\n", "\n").strip()
    if not text:
        raise BusinessError("The message is empty")
    if len(text) > 2000:
        raise BusinessError("The message is too long (2000 characters at most)")
    if not _SLOT.search(text):
        raise BusinessError("Write exactly four stars **** where the customer's outstanding amount should "
                            "appear. (The message has no ****.)")
    return text


def render(text, amount) -> str:
    """The message for one customer: every **** (or (****)) becomes his balance, e.g. 12,500."""
    out = _SLOT.sub(f"{r2(amount):,.0f}", text or "")
    if _SLOT.search(out):                                   # can never happen; a message with stars is not sent
        raise BusinessError("The message still contains ****")
    return out


def count_slots(text) -> int:
    return len(_SLOT.findall(text or ""))


def current(db) -> dict:
    """{'text', 'version', 'updated_at', 'updated_by'}. Version 0 = never edited (the standard message)."""
    saved = settings_store.get(db, KEY_TEMPLATE)
    if saved and saved.get("text"):
        return saved
    text = default_text(db)
    try:                                                    # message written in an older version (it used xxxxxx)
        from . import backup
        old = (backup.get_settings(db.data_dir).get("sms_template") or "").strip()
        if old and _OLD.search(old):
            text = _OLD.sub("(****)", old)
    except Exception:
        pass
    return {"text": text, "version": 0, "updated_at": "", "updated_by": ""}


def save(db, text, base_version=None, by="Windows") -> dict:
    """Save a new message. base_version = the version the editor started from (None = do not check)."""
    text = check(text)
    cur = current(db)
    if base_version is not None and int(base_version) != cur["version"]:
        raise TemplateConflict(cur)
    if text == cur["text"] and cur["version"] > 0:
        return cur
    new = {"text": text, "version": cur["version"] + 1, "updated_at": now(), "updated_by": by}
    settings_store.save(db, KEY_TEMPLATE, new)
    return new


def restore_default(db, base_version=None, by="Windows") -> dict:
    return save(db, default_text(db), base_version, by)
