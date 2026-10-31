"""CSV / Excel / PDF output for any report dict (see builders.py)."""
import csv
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .invoice_pdf import ACCENT, _esc, _fonts


def export_csv(report, path):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:  # utf-8-sig: Excel shows Urdu correctly
        w = csv.writer(f)
        w.writerow([report["title"], report.get("subtitle", "")])
        w.writerow(report["headers"])
        w.writerows(report["rows"])
        for label, value in report["summary"]:
            w.writerow([label, value])
    return str(path)


def _num(text):
    try:
        return float(str(text).replace(",", ""))
    except ValueError:
        return text


def export_xlsx(report, path):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    wb = Workbook()
    ws = wb.active
    ws.title = report["title"][:30]
    ws.append([report["title"]])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append([report.get("subtitle", "")])
    ws.append(report["headers"])
    for c in ws[3]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1B6EF3")
    for i, row in enumerate(report["rows"]):
        ws.append([_num(v) if j in report["numeric"] else v for j, v in enumerate(row)])
        for j in report["numeric"]:
            ws.cell(row=ws.max_row, column=j + 1).number_format = "#,##0.00"
            ws.cell(row=ws.max_row, column=j + 1).alignment = Alignment(horizontal="right")
        if i in report["bold_rows"]:
            for c in ws[ws.max_row]:
                c.font = Font(bold=True)
    ws.append([])
    for label, value in report["summary"]:
        ws.append([label, _num(value)])
        ws[ws.max_row][0].font = Font(bold=True)
    for col in ws.columns:
        width = max(len(str(c.value)) for c in col if c.value is not None) if any(c.value is not None for c in col) else 8
        ws.column_dimensions[col[0].column_letter].width = min(max(width + 2, 10), 50)
    wb.save(path)
    return str(path)


def build_table_pdf(report, company, path):
    """Any report as a PDF (landscape when there are many columns)."""
    reg, bold = _fonts()
    ncols = len(report["headers"])
    size = landscape(A4) if ncols > 6 else A4
    usable = size[0] - 24 * mm - 12
    st = lambda n, **k: ParagraphStyle(n, **{"fontName": reg, "fontSize": 8.5, "leading": 11, **k})
    num = report["numeric"]
    story = [Paragraph(_esc(company["name"]).upper(), st("c", fontName=bold, fontSize=14, leading=18, textColor=ACCENT)),
             Paragraph(f"<b>{_esc(report['title'])}</b> &nbsp; {_esc(report.get('subtitle', ''))}", st("t", fontSize=10, leading=14)),
             Spacer(1, 3 * mm)]
    head = [Paragraph(_esc(h), st("h", fontName=bold, textColor=colors.white, alignment=TA_RIGHT if i in num else 0))
            for i, h in enumerate(report["headers"])]
    data = [head]
    for i, row in enumerate(report["rows"]):
        data.append([Paragraph(_esc(v), st("b", fontName=bold if i in report["bold_rows"] else reg,
                                           alignment=TA_RIGHT if j in num else 0)) for j, v in enumerate(row)])
    # give text columns more room than numeric ones
    weights = [1.0 if j in num else 2.2 for j in range(ncols)]
    widths = [usable * w / sum(weights) for w in weights]
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), ACCENT), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f8ff")]),
                           ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor("#e5e9f0")),
                           ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    story.append(t)
    if report["summary"]:
        story.append(Spacer(1, 4 * mm))
        s = Table([[Paragraph(_esc(a), st("sa", fontName=bold)), Paragraph(_esc(b), st("sb", alignment=TA_RIGHT))]
                   for a, b in report["summary"]], colWidths=[55 * mm, 40 * mm], hAlign="RIGHT")
        story.append(s)
    SimpleDocTemplate(str(path), pagesize=size, leftMargin=12 * mm, rightMargin=12 * mm, topMargin=12 * mm,
                      bottomMargin=12 * mm, title=report["title"], author=company["name"]).build(story)
    return str(path)
