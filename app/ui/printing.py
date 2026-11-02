"""Create the invoice PDF in the data folder and open it (the viewer prints with Ctrl+P)."""
import os
import subprocess
import sys
from pathlib import Path

from ..reports.invoice_pdf import build_invoice_pdf
from ..services import backup


def resolve_size(db, size: str) -> str:
    """'Thermal' -> the roll width chosen in Printer Settings ('80mm' / '58mm')."""
    if size == "Thermal":
        return f"{int(backup.get_settings(db.data_dir).get('thermal_width', 80))}mm"
    return size


def invoice_pdf_path(db, invoice_id: int, size: str) -> Path:
    no = db.scalar("SELECT no FROM invoices WHERE id=?", (invoice_id,), "")
    suffix = "" if size == "A4" else f"_{size}"
    return Path(db.data_dir) / "invoices" / f"{no}{suffix}.pdf"


def deliver(db, path, thermal: bool) -> str:
    """Send the PDF to the printer chosen in Printer Settings, or open it in the PDF viewer.
    Returns 'printer' or 'viewer'. If direct printing fails the bill is still opened in the viewer."""
    s = backup.get_settings(db.data_dir)
    printer = s.get("thermal_printer" if thermal else "a4_printer", "")
    if printer:
        try:
            from .direct_print import direct_print
            direct_print(path, None if printer == "__default__" else printer)
            return "printer"
        except Exception:
            pass
    open_file(path)
    return "viewer"


def print_invoice(db, invoice_id: int, size: str = "A4") -> Path:
    size = resolve_size(db, size)
    path = invoice_pdf_path(db, invoice_id, size)
    path.parent.mkdir(parents=True, exist_ok=True)
    build_invoice_pdf(db, invoice_id, path, size)
    deliver(db, path, thermal=size != "A4")
    return path


def open_file(path):
    if sys.platform.startswith("win"):
        os.startfile(str(path))  # noqa: S606 - opens in the default PDF viewer
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def print_purchase(db, purchase_id: int) -> Path:
    from ..reports.doc_pdf import build_purchase_pdf
    no = db.scalar("SELECT no FROM purchases WHERE id=?", (purchase_id,), "")
    path = Path(db.data_dir) / "invoices" / f"{no}.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    build_purchase_pdf(db, purchase_id, path)
    deliver(db, path, thermal=False)
    return path


def print_voucher(db, voucher_no: str) -> Path:
    from ..reports.doc_pdf import build_voucher_pdf
    path = Path(db.data_dir) / "invoices" / f"{voucher_no}.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    build_voucher_pdf(db, voucher_no, path)
    deliver(db, path, thermal=False)
    return path
