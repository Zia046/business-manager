"""All Reports-menu screens, Outstanding, Sale Summary, and Invoice Print (view/edit/cancel)."""
from PySide6.QtWidgets import QMessageBox

from ..reports import builders as B
from ..services import trading
from ..services.common import BusinessError
from .printing import print_invoice
from .report_window import ReportWindow
from .sale_invoice import SaleInvoiceDialog


def _simple(builder, title, use_dates=True, filter_kind=None):
    return lambda win: ReportWindow(win.db, builder, title, use_dates=use_dates, filter_kind=filter_kind,
                                    parent=win).exec()


def open_invoice_print(win):
    def invoice_id(rw):
        no = rw.selected_first_cell()
        if not no:
            QMessageBox.information(rw, "Select", "Select an invoice row first.")
            return None
        return rw.db.scalar("SELECT id FROM invoices WHERE no=?", (no,), None)

    def do_print(size):
        def run(rw):
            iid = invoice_id(rw)
            if iid:
                try:
                    print_invoice(rw.db, iid, size)
                except Exception as exc:
                    QMessageBox.warning(rw, "Print", f"Could not print:\n{exc}")
        return run

    def edit(rw):
        iid = invoice_id(rw)
        if not iid:
            return
        if rw.db.scalar("SELECT status FROM invoices WHERE id=?", (iid,), "") == "cancelled":
            QMessageBox.information(rw, "Cancelled", "A cancelled invoice cannot be edited.")
            return
        try:
            SaleInvoiceDialog(rw.db, rw, invoice_id=iid).exec()
        except BusinessError as exc:
            QMessageBox.warning(rw, "Edit", str(exc))
        rw.reload()

    def cancel(rw):
        iid = invoice_id(rw)
        if not iid:
            return
        no = rw.selected_first_cell()
        if QMessageBox.question(rw, "Cancel invoice", f"Cancel invoice {no}?\n\nStock will be returned and the "
                                "customer's account and cash book will be corrected.") != QMessageBox.Yes:
            return
        try:
            trading.cancel_invoice(rw.db, iid)
        except BusinessError as exc:
            QMessageBox.warning(rw, "Cancel", str(exc))
        rw.reload()

    ReportWindow(win.db, B.invoice_list_report, "Invoice Print", parent=win,
                 actions=[("Print A4", do_print("A4")), ("Print Thermal", do_print("Thermal")),
                          ("View / Edit", edit), ("Cancel Invoice", cancel)]).exec()


SCREENS = {
    "customer_transactions": _simple(B.customer_transactions_report, "Customer Transactions", filter_kind="customer"),
    "cash_received_report": _simple(B.cash_received_report, "Cash Received"),
    "profit_loss": _simple(B.profit_loss_report, "Profit & Loss"),
    "invoice_wise": _simple(B.invoice_wise_report, "Invoice Wise Sale Summary"),
    "stock_position": _simple(B.stock_position_report, "Stock Position", use_dates=False),
    "product_ledger": _simple(B.product_ledger_report, "Products Ledger", filter_kind="product"),
    "all_balances": _simple(B.all_customer_balance_report, "All Customer Balance", use_dates=False),
    "products_report": _simple(B.products_report, "Products", use_dates=False),
    "outstanding": _simple(B.outstanding_report, "Outstanding / Baqayajat", use_dates=False),
    "sale_summary": _simple(B.sale_summary_report, "Sale Summary"),
    "invoice_print": open_invoice_print,
}
