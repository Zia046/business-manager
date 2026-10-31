"""Create the invoice PDF in the data folder and open it (the viewer prints with Ctrl+P)."""
import os
import subprocess
import sys
from pathlib import Path

from ..reports.invoice_pdf import build_invoice_pdf


def invoice_pdf_path(db, invoice_id: int, size: str) -> Path:
    no = db.scalar("SELECT no FROM invoices WHERE id=?", (invoice_id,), "")
    suffix = "" if size == "A4" else "_80mm"
    return Path(db.data_dir) / "invoices" / f"{no}{suffix}.pdf"


def print_invoice(db, invoice_id: int, size: str = "A4") -> Path:
    path = invoice_pdf_path(db, invoice_id, size)
    path.parent.mkdir(parents=True, exist_ok=True)
    build_invoice_pdf(db, invoice_id, path, size)
    open_file(path)
    return path


def open_file(path):
    if sys.platform.startswith("win"):
        os.startfile(str(path))  # noqa: S606 - opens in the default PDF viewer
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])
