"""Invoice PDF: A4 and 80mm thermal receipt. Profit/loss is NEVER printed."""
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle)

from ..config import SOFTWARE_CONTACT_LINE
from ..services.common import add_months
from ..services import reports

ACCENT = colors.HexColor("#1b6ef3")
_FONT_CACHE = {}

# Unicode fonts: Windows first, then common Linux paths (for development/tests).
_FONT_CANDIDATES = [
    ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/segoeuib.ttf"),
    ("C:/Windows/Fonts/tahoma.ttf", "C:/Windows/Fonts/tahomabd.ttf"),
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
]


def _fonts():
    if "f" not in _FONT_CACHE:
        for reg, bold in _FONT_CANDIDATES:
            if Path(reg).exists() and Path(bold).exists():
                pdfmetrics.registerFont(TTFont("BM", reg))
                pdfmetrics.registerFont(TTFont("BM-Bold", bold))
                _FONT_CACHE["f"] = ("BM", "BM-Bold")
                break
        else:
            _FONT_CACHE["f"] = ("Helvetica", "Helvetica-Bold")
    return _FONT_CACHE["f"]


def _shape(text: str) -> str:
    """Join/reorder Urdu/Arabic letters if the optional libraries are installed."""
    text = text or ""
    if any("\u0600" <= ch <= "\u06ff" for ch in text):
        try:
            import arabic_reshaper
            from bidi.algorithm import get_display
            return get_display(arabic_reshaper.reshape(text))
        except ImportError:
            pass
    return text


def _esc(s) -> str:
    return _shape(str(s or "")).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _m(x) -> str:
    return f"{x:,.2f}"


def _qty(x) -> str:
    return f"{x:g}"


def _imei_html(it, small: int) -> str:
    """IMEI line(s) printed under a phone: 'IMEI: x' or 'IMEI 1: x / IMEI 2: y'."""
    if not it.get("serial"):
        return ""
    if it.get("serial2"):
        text = f"IMEI 1: {_esc(it['serial'])}<br/>IMEI 2: {_esc(it['serial2'])}"
    else:
        text = f"IMEI: {_esc(it['serial'])}"
    return f"<br/><font size={small} color='#374151'>{text}</font>"


def _warranty_html(it, sale_date: str, small: int) -> str:
    months = it.get("warranty_months") or 0
    if not months:
        return ""
    until = add_months(sale_date[:10], months)
    return (f"<br/><font size={small} color='#374151'>Warranty: {months} month(s), till "
            f"{until[8:10]}-{until[5:7]}-{until[:4]}</font>")


def build_invoice_pdf(db, invoice_id: int, out_path, size: str = "A4") -> str:
    """size: 'A4', or a thermal roll width such as '80mm' / '58mm'. Returns the file path."""
    d = reports.invoice_detail(db, invoice_id)
    if d is None:
        raise ValueError("Invoice not found")
    thermal = size != "A4"
    roll_mm = int(size[:-2]) if thermal else 0
    reg, bold = _fonts()
    inv, co, party = d["invoice"], d["company"], d["party"]
    fs = 8 if thermal else 10
    page_w = roll_mm * mm if thermal else A4[0]
    margin = (3 if roll_mm <= 58 else 4) * mm if thermal else 16 * mm
    usable = page_w - 2 * margin - 12  # 12pt = default frame padding, keeps tables aligned with text

    def st(name, **kw):
        base = dict(fontName=reg, fontSize=fs, leading=fs * 1.3)
        base.update(kw)
        return ParagraphStyle(name, **base)

    s_norm, s_bold = st("n"), st("b", fontName=bold)
    s_right = st("r", alignment=TA_RIGHT)
    s_center = st("c", alignment=TA_CENTER)
    s_name = st("name", fontName=bold, fontSize=fs + (5 if not thermal else 3), leading=(fs + 8),
                alignment=TA_CENTER if thermal else 0, textColor=colors.black if thermal else ACCENT)
    s_head = st("h", fontName=bold, textColor=colors.white)

    story = []
    logo = None
    if co["logo_path"] and Path(co["logo_path"]).exists():
        sz = 16 * mm if thermal else 24 * mm
        logo = Image(co["logo_path"], width=sz, height=sz, kind="proportional")

    name_p = Paragraph(_esc(co["name"]).upper(), s_name)
    contact = Paragraph("<br/>".join(_esc(x) for x in (co["address"], f"Mobile: {co['phone']}",
                                                      co["email"]) if x), st("ct", textColor=colors.HexColor("#4b5563"))
                        if not thermal else s_center)
    if thermal:
        if logo:
            logo.hAlign = "CENTER"
            story.append(logo)
        story += [name_p, contact, Spacer(1, 3 * mm)]
    else:
        head = Table([[logo or "", [name_p, contact]]], colWidths=[28 * mm, usable - 28 * mm])
        head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                  ("LINEBELOW", (0, 0), (-1, 0), 1.5, ACCENT),
                                  ("BOTTOMPADDING", (0, 0), (-1, 0), 8)]))
        story += [head, Spacer(1, 6 * mm)]

    title = "SALE INVOICE" + ("  (CANCELLED)" if inv["status"] == "cancelled" else "")
    meta_rows = [[Paragraph(f"<b>{title}</b>", st("t", fontName=bold, fontSize=fs + 3, textColor=ACCENT)), ""],
                 [Paragraph(f"Invoice No: <b>{_esc(inv['no'])}</b>", s_norm),
                  Paragraph(f"Date: {inv['date'][:16]}", s_right)],
                 [Paragraph(f"Customer: <b>{_esc(party['name'])}</b>", s_norm),
                  Paragraph(_esc(party["phone"]) if party["phone"] else "", s_right)]]
    if thermal:  # narrow roll: stack the lines instead of two columns
        meta_rows = [meta_rows[0], [Paragraph(f"Invoice No: <b>{_esc(inv['no'])}</b>", s_norm), ""],
                     [Paragraph(f"Date: {inv['date'][:16]}", s_norm), ""],
                     [Paragraph(f"Customer: <b>{_esc(party['name'])}</b>", s_norm), ""]]
        if party["phone"]:
            meta_rows.append([Paragraph(_esc(party["phone"]), s_norm), ""])
    meta = Table(meta_rows, colWidths=[usable * 0.6, usable * 0.4])
    meta.setStyle(TableStyle([("SPAN", (0, 0), (1, 0))] + ([("SPAN", (0, r), (1, r)) for r in range(1, len(meta_rows))] if thermal else []) + [ ("TOPPADDING", (0, 0), (-1, -1), 1),
                              ("BOTTOMPADDING", (0, 0), (-1, -1), 1), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                              ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story += [meta, Spacer(1, 3 * mm)]

    # ---- items table ----
    if thermal:
        rows = [[Paragraph("Item", s_head), Paragraph("Qty", s_head), Paragraph("Amount", st("hr", fontName=bold, textColor=colors.white, alignment=TA_RIGHT))]]
        widths = [usable * 0.52, usable * 0.14, usable * 0.34]
        for it in d["items"]:
            amount = it["qty"] * it["price"] - it["discount"]
            rows.append([Paragraph(f"{_esc(it['product_name'])}{_imei_html(it, fs - 1)}{_warranty_html(it, inv['date'], fs - 1)}<br/>@ {_m(it['price'])}", s_norm),
                         Paragraph(_qty(it["qty"]), s_norm), Paragraph(_m(amount), s_right)])
        numeric = (1, 2)
    else:
        hr = st("hr", fontName=bold, textColor=colors.white, alignment=TA_RIGHT)
        rows = [[Paragraph("#", s_head), Paragraph("Description", s_head), Paragraph("Qty", hr),
                 Paragraph("Price", hr), Paragraph("Disc.", hr), Paragraph("Amount", hr)]]
        widths = [10 * mm, usable - 10 * mm - 18 * mm - 30 * mm - 24 * mm - 32 * mm,
                  18 * mm, 30 * mm, 24 * mm, 32 * mm]
        for i, it in enumerate(d["items"], 1):
            amount = it["qty"] * it["price"] - it["discount"]
            desc = _esc(it["product_name"]) + _imei_html(it, fs - 1) + _warranty_html(it, inv["date"], fs - 1)
            rows.append([Paragraph(str(i), s_norm), Paragraph(desc, s_norm), Paragraph(_qty(it["qty"]), s_right),
                         Paragraph(_m(it["price"]), s_right), Paragraph(_m(it["discount"]) if it["discount"] else "-", s_right),
                         Paragraph(_m(amount), s_right)])
    items = Table(rows, colWidths=widths, repeatRows=1)
    items.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f8ff")]),
        ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor("#e5e9f0")),
        ("TOPPADDING", (0, 0), (-1, -1), 3 if thermal else 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3 if thermal else 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 3 if thermal else 6), ("RIGHTPADDING", (0, 0), (-1, -1), 3 if thermal else 6)]))
    story += [items, Spacer(1, 3 * mm)]

    # ---- totals ----
    t = [["Sub Total", _m(inv["subtotal"])]]
    if inv["discount"]:
        t.append(["Discount", "- " + _m(inv["discount"])])
    t += [["GRAND TOTAL", _m(inv["total"])], ["Paid", _m(inv["paid"])], ["Balance Due", _m(d["balance_due"])]]
    if not party["is_walkin"]:
        t.append(["Account Balance", _m(d["account_balance"])])
    trows = [[Paragraph(a, s_bold if a in ("GRAND TOTAL", "Balance Due") else s_norm),
              Paragraph(b, st("tr", alignment=TA_RIGHT, fontName=bold if a in ("GRAND TOTAL", "Balance Due") else reg))]
             for a, b in t]
    tw = usable if thermal else usable * 0.5
    totals = Table(trows, colWidths=[tw * 0.55, tw * 0.45], hAlign="RIGHT")
    gt = [i for i, (a, _) in enumerate(t) if a == "GRAND TOTAL"][0]
    totals.setStyle(TableStyle([("BACKGROUND", (0, gt), (-1, gt), colors.HexColor("#e8f0fe")),
                                ("LINEABOVE", (0, gt), (-1, gt), 1, ACCENT),
                                ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    story += [totals]

    if inv["note"]:
        story += [Spacer(1, 4 * mm), Paragraph(f"<b>Note:</b> {_esc(inv['note']).replace(chr(10), '<br/>')}", s_norm)]
    story += [Spacer(1, 6 * mm),
              Paragraph("Thank you for your business!", st("ty", fontName=bold, alignment=TA_CENTER,
                                                           textColor=ACCENT if not thermal else colors.black)),
              Spacer(1, 2 * mm),
              Paragraph(_esc(SOFTWARE_CONTACT_LINE), st("sw", fontSize=7 if not thermal else 6, alignment=TA_CENTER,
                                                         textColor=colors.grey))]

    out_path = str(out_path)
    if thermal:  # continuous roll: measure the content, then size the page to fit
        h = sum(f.wrap(usable, 10000)[1] for f in story) + 2 * margin + 6 * mm
        pagesize = (page_w, max(h, 60 * mm))
    else:
        pagesize = A4
    SimpleDocTemplate(out_path, pagesize=pagesize, leftMargin=margin, rightMargin=margin,
                      topMargin=margin, bottomMargin=margin, title=inv["no"],
                      author=co["name"]).build(story)
    return out_path
