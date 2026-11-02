"""Import products, customers and suppliers from an Excel (.xlsx) or CSV file.

Every row is checked first (dry run) so the shopkeeper sees what will happen, and a bad row never stops
the good ones. Phones can be imported as products, but their stock must come through Stock Purchase
because every phone needs its IMEI number."""
import csv
import re
from pathlib import Path

from . import masters
from .common import BusinessError

PRODUCT_COLUMNS = ["Name", "Category", "Sale Price", "Purchase Price", "Opening Stock", "Tags", "Unit",
                   "Low Stock Level", "Warranty Months"]
PARTY_COLUMNS = ["Name", "Phone", "Address", "Opening Balance"]
_EXAMPLES = {
    "products": [["Samsung A15 128GB", "Mobile Phone", 42000, 38000, 0, "#samsung #android", "pcs", 2, 12],
                 ["Fast Charger 25W", "Accessories", 1200, 800, 20, "#charger", "pcs", 5, 6]],
    "customers": [["Ali Khan", "03001234567", "Daggar, Buner", 0]],
    "suppliers": [["Phone Wholesaler", "03111234567", "Peshawar", 0]],
}


def _key(text) -> str:
    return re.sub(r"[^a-z0-9]", "", str(text or "").lower())


def write_template(path, kind: str):
    """Empty Excel file with the right column names and one or two example rows."""
    from openpyxl import Workbook
    from openpyxl.styles import Font
    cols = PRODUCT_COLUMNS if kind == "products" else PARTY_COLUMNS
    wb = Workbook()
    ws = wb.active
    ws.title = kind.title()
    ws.append(cols)
    for c in ws[1]:
        c.font = Font(bold=True)
    for row in _EXAMPLES[kind]:
        ws.append(row)
    for col in ws.columns:
        ws.column_dimensions[col[0].column_letter].width = 22
    notes = wb.create_sheet("Notes")
    notes.append(["Delete the example rows, type your own, save, then use Import in the software."])
    if kind == "products":
        notes.append(["Category must be one that exists in the software (New Account > Categories)."])
        notes.append(["Mobile phones: opening stock is ignored. Add phone stock through Stock Purchase with IMEI numbers."])
    else:
        notes.append(["Opening Balance: positive = they owe you (customer) / you owe them (supplier)."])
    wb.save(path)
    return str(path)


def read_rows(path) -> list[dict]:
    """Rows of the file as {normalised column name: value}. Empty rows are dropped."""
    path = Path(path)
    if path.suffix.lower() == ".csv":
        raw = None
        for enc in ("utf-8-sig", "cp1252"):
            try:
                raw = list(csv.reader(path.read_text(encoding=enc).splitlines()))
                break
            except UnicodeDecodeError:
                continue
    elif path.suffix.lower() in (".xlsx", ".xlsm"):
        from openpyxl import load_workbook
        wb = load_workbook(path, read_only=True, data_only=True)
        raw = [list(r) for r in wb.worksheets[0].iter_rows(values_only=True)]
        wb.close()
    else:
        raise BusinessError("Choose an Excel (.xlsx) or CSV file")
    if not raw:
        raise BusinessError("The file is empty")
    head = [_key(h) for h in raw[0]]
    out = []
    for i, r in enumerate(raw[1:], start=2):
        if not any(str(c).strip() for c in r if c is not None):
            continue
        d = {head[j]: (r[j] if j < len(r) else None) for j in range(len(head)) if head[j]}
        d["_line"] = i
        out.append(d)
    return out


def _num(v, label):
    if v is None or str(v).strip() == "":
        return 0.0
    try:
        return float(str(v).replace(",", "").replace("Rs", "").strip())
    except ValueError:
        raise BusinessError(f"{label} '{v}' is not a number")


def _txt(v) -> str:
    if v is None:
        return ""
    return str(int(v)) if isinstance(v, float) and v.is_integer() else str(v).strip()


def _check_columns(rows, required):
    if rows and not all(_key(c) in rows[0] for c in required):
        raise BusinessError("The file does not have the columns: " + ", ".join(required))


def import_products(db, rows, dry_run=False) -> list[dict]:
    """Returns one result per row: {line, name, status: 'new'|'skip'|'error', message}."""
    _check_columns(rows, ["Name", "Category"])
    existing = {r["name"].lower() for r in db.query("SELECT name FROM products WHERE active=1")}
    seen, out = set(), []
    for r in rows:
        name = _txt(r.get("name"))
        res = {"line": r["_line"], "name": name, "status": "new", "message": ""}
        try:
            if not name:
                raise BusinessError("Name is empty")
            if name.lower() in existing or name.lower() in seen:
                res.update(status="skip", message="A product with this name already exists")
                out.append(res)
                continue
            cat = masters.get_category(db, _txt(r.get("category")))
            if not cat:
                raise BusinessError(f"Category '{_txt(r.get('category'))}' does not exist")
            opening = _num(r.get("openingstock"), "Opening Stock")
            if cat["is_mobile"] and opening:
                res["message"] = "Phone: stock not imported (add it through Stock Purchase with IMEI numbers)"
                opening = 0.0
            args = dict(name=name, sale_price=_num(r.get("saleprice"), "Sale Price"),
                        purchase_price=_num(r.get("purchaseprice"), "Purchase Price"), opening_stock=opening,
                        category=cat["name"], tags=_txt(r.get("tags")), unit=_txt(r.get("unit")) or "pcs",
                        low_stock_level=_num(r.get("lowstocklevel"), "Low Stock Level"),
                        warranty_months=int(_num(r.get("warrantymonths"), "Warranty Months")))
            if cat["is_mobile"]:
                args["imei_mode"] = "double"
                res["message"] = (res["message"] + "; " if res["message"] else "") + "set as Double IMEI (change in Products if single)"
            if not dry_run:
                masters.add_product(db, **args)
            seen.add(name.lower())
        except BusinessError as exc:
            res.update(status="error", message=str(exc))
        out.append(res)
    return out


def import_parties(db, rows, kind, dry_run=False) -> list[dict]:
    _check_columns(rows, ["Name"])
    existing = {r["name"].lower() for r in db.query("SELECT name FROM parties WHERE kind=? AND active=1", (kind,))}
    seen, out = set(), []
    for r in rows:
        name = _txt(r.get("name"))
        res = {"line": r["_line"], "name": name, "status": "new", "message": ""}
        try:
            if not name:
                raise BusinessError("Name is empty")
            if name.lower() in existing or name.lower() in seen:
                res.update(status="skip", message="This name already exists")
                out.append(res)
                continue
            bal = _num(r.get("openingbalance"), "Opening Balance")
            if not dry_run:
                masters.add_party(db, kind, name, _txt(r.get("phone")), _txt(r.get("address")), bal)
            seen.add(name.lower())
        except BusinessError as exc:
            res.update(status="error", message=str(exc))
        out.append(res)
    return out
