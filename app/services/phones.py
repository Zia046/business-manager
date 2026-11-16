"""Mobile-phone details (type, RAM, storage, condition) and the list of phones that are in stock now.

The details live on the product line the phone belongs to; every IMEI points to its product, so each
phone keeps its details when it is sold. Old records without details keep working (they show '-')."""
from .common import BusinessError, r2

TYPES = {"smartphone": "Smartphone", "keypad": "Keypad / Simple Mobile"}
CONDITIONS = {"new": "New", "used": "Used"}


def _gb(value, label):
    if value in (None, "", 0, "0"):
        return None
    try:
        n = int(float(value))
    except (TypeError, ValueError):
        raise BusinessError(f"{label} must be a number (GB), e.g. 8")
    if n <= 0 or n > 4096:
        raise BusinessError(f"{label} must be between 1 and 4096 GB")
    return n


def clean(mobile_type=None, ram_gb=None, storage_gb=None, condition=None, brand="") -> dict:
    """Checked values ready to be saved. A smartphone needs RAM and storage; a keypad phone has neither.
    mobile_type None = not said (records made before this feature, or imported lists): nothing is required."""
    mobile_type = (mobile_type or "").strip().lower() or None
    if mobile_type not in (None, *TYPES):
        raise BusinessError("Mobile type must be Smartphone or Keypad / Simple Mobile")
    condition = (condition or "").strip().lower() or None
    if condition not in (None, *CONDITIONS):
        raise BusinessError("Condition must be New or Used")
    ram, storage = _gb(ram_gb, "RAM"), _gb(storage_gb, "Storage")
    if mobile_type == "keypad":
        ram = storage = None
    elif mobile_type == "smartphone" and (ram is None or storage is None):
        raise BusinessError("Enter RAM and Storage (GB) for a smartphone, e.g. RAM 8, Storage 256")
    return {"brand": (brand or "").strip() or None, "mobile_type": mobile_type, "ram_gb": ram,
            "storage_gb": storage, "condition": condition}


def gb(value) -> str:
    return f"{int(value)} GB" if value else "-"


def spec(p) -> str:
    """Short text for lists: '8 GB / 256 GB', 'Keypad', or '' for an old record."""
    if p.get("mobile_type") == "keypad":
        return "Keypad"
    if p.get("ram_gb") or p.get("storage_gb"):
        return f"{gb(p.get('ram_gb'))} / {gb(p.get('storage_gb'))}"
    return ""


def condition_of(p) -> str:
    c = p.get("condition")
    if c in CONDITIONS:
        return c
    return "used" if "(2nd hand)" in (p.get("name") or "").lower() else "new"


def in_stock(db, text="", condition="", mobile_type="", ram=None, storage=None, sort="model", descending=False):
    """Every phone that is in the shop now (one row per IMEI). Sold phones are simply not in this list.
    text searches brand, model and IMEI. sort: model | purchase | sale | ram | storage."""
    rows = db.query(
        "SELECT s.id AS serial_id, s.serial AS imei1, s.imei2, p.id AS product_id, p.name, p.brand, p.category, "
        "p.mobile_type, p.ram_gb, p.storage_gb, p.condition, p.avg_cost, p.sale_price AS product_sale_price, "
        "pu.no AS purchase_no, pu.date AS purchase_date, "
        "(SELECT pi.price FROM purchase_items pi WHERE pi.purchase_id=s.purchase_id AND pi.product_id=s.product_id "
        " LIMIT 1) AS unit_price, up.sale_price AS used_sale_price, up.seller_name "
        "FROM serials s JOIN products p ON p.id=s.product_id "
        "LEFT JOIN purchases pu ON pu.id=s.purchase_id "
        "LEFT JOIN used_phones up ON up.purchase_id=s.purchase_id AND up.imei1=s.serial "
        "WHERE s.status='in_stock'")
    text, out = (text or "").strip().lower(), []
    for r in rows:
        r["condition"] = condition_of(r)
        r["purchase_price"] = r2(r["unit_price"] if r["unit_price"] is not None else r["avg_cost"])
        r["sale_price"] = r2(r["used_sale_price"] or r["product_sale_price"] or 0)
        r["brand"] = r["brand"] or ""
        r["status"] = "Available"
        if condition and r["condition"] != condition:
            continue
        if mobile_type and (r["mobile_type"] or "") != mobile_type:
            continue
        if ram and r["ram_gb"] != int(ram):
            continue
        if storage and r["storage_gb"] != int(storage):
            continue
        if text and text not in " ".join((r["brand"], r["name"], r["imei1"], r["imei2"] or "")).lower():
            continue
        out.append(r)
    keys = {"model": lambda r: ((r["brand"] + " " + r["name"]).strip().lower(), r["imei1"]),
            "purchase": lambda r: r["purchase_price"], "sale": lambda r: r["sale_price"],
            "ram": lambda r: r["ram_gb"] or 0, "storage": lambda r: r["storage_gb"] or 0}
    out.sort(key=keys.get(sort, keys["model"]), reverse=bool(descending))
    return out


def filter_values(db) -> dict:
    """The RAM and storage sizes that exist among the phones in stock (for the filter boxes)."""
    rows = db.query("SELECT DISTINCT p.ram_gb, p.storage_gb FROM serials s JOIN products p ON p.id=s.product_id "
                    "WHERE s.status='in_stock'")
    return {"ram": sorted({r["ram_gb"] for r in rows if r["ram_gb"]}),
            "storage": sorted({r["storage_gb"] for r in rows if r["storage_gb"]})}
