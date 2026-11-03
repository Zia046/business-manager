"""Price/barcode labels. Two layouts:
   'sheet'  : A4 sheet of sticker labels (3 columns x 7 rows, 70 x 38 mm)
   'roll'   : one label per page on a label printer roll (default 50 x 30 mm)"""
from pathlib import Path

from reportlab.graphics.barcode import code128
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from ..services.masters import barcode_for
from .invoice_pdf import _fonts

SHEET = dict(cols=3, rows=7, w=70 * mm, h=38 * mm)


def _fit(c, text, font, size, width):
    while size > 5 and c.stringWidth(text, font, size) > width:
        size -= 0.5
    return size


def _label(c, x, y, w, h, shop, product, price):
    reg, bold = _fonts()
    pad = 2.5 * mm
    c.setFont(reg, 6.5)
    c.drawCentredString(x + w / 2, y + h - 4 * mm, shop[:40])
    name = product["name"]
    size = _fit(c, name, bold, 9, w - 2 * pad)
    c.setFont(bold, size)
    c.drawCentredString(x + w / 2, y + h - 8.5 * mm, name)
    c.setFont(bold, 13)
    c.drawCentredString(x + w / 2, y + h - 14 * mm, f"Rs. {price:,.0f}")
    code = barcode_for(product)
    bc = code128.Code128(code, barHeight=h - 24 * mm if h > 28 * mm else 8 * mm, barWidth=0.33 * mm,
                         humanReadable=False)
    scale = min(1.0, (w - 2 * pad) / bc.width)
    c.saveState()
    c.translate(x + (w - bc.width * scale) / 2, y + 5.5 * mm)
    c.scale(scale, 1)
    bc.drawOn(c, 0, 0)
    c.restoreState()
    c.setFont(reg, 6.5)
    c.drawCentredString(x + w / 2, y + 2 * mm, code)


def build_labels_pdf(db, items, out_path, layout="sheet", roll_mm=(50, 30)) -> str:
    """items: [(product_id, copies)]. Returns the PDF path."""
    shop = db.scalar("SELECT name FROM company WHERE id=1", (), "")
    labels = []
    for pid, copies in items:
        p = db.one("SELECT * FROM products WHERE id=?", (pid,))
        if p:
            labels += [p] * max(int(copies), 0)
    if not labels:
        raise ValueError("Choose at least one product")
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    if layout == "roll":
        w, h = roll_mm[0] * mm, roll_mm[1] * mm
        c = canvas.Canvas(str(out_path), pagesize=(w, h))
        for p in labels:
            _label(c, 0, 0, w, h, shop, p, p["sale_price"])
            c.showPage()
    else:
        c = canvas.Canvas(str(out_path), pagesize=A4)
        per_page = SHEET["cols"] * SHEET["rows"]
        left = (A4[0] - SHEET["cols"] * SHEET["w"]) / 2
        top = (A4[1] - SHEET["rows"] * SHEET["h"]) / 2 + SHEET["rows"] * SHEET["h"]
        for i, p in enumerate(labels):
            k = i % per_page
            col, row = k % SHEET["cols"], k // SHEET["cols"]
            x, y = left + col * SHEET["w"], top - (row + 1) * SHEET["h"]
            c.setStrokeGray(0.8)
            c.rect(x, y, SHEET["w"], SHEET["h"])
            _label(c, x, y, SHEET["w"], SHEET["h"], shop, p, p["sale_price"])
            if k == per_page - 1 and i != len(labels) - 1:
                c.showPage()
        c.showPage()
    c.save()
    return str(out_path)
