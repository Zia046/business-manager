"""Maps a menu/button key to the code that opens that screen.

Later steps add entries here; anything not registered shows a placeholder.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from ..config import APP_NAME
from . import dialogs
from .parties import PartiesWindow
from .products import ProductsWindow
from .report_screens import SCREENS
from .returns_ui import ReturnDialog
from .backup_ui import BackupDialog, restore_dialog
from .account_screens import open_balance_sheet, open_cash_book, open_vouchers
from .cash_recovery import CashRecoveryDialog
from .categories_ui import CategoriesDialog
from .reset_ui import ResetDialog
from .payments_ui import PaymentDialog
from .sale_invoice import SaleInvoiceDialog
from .stock_purchase import StockPurchaseDialog


def _company_edit(win):
    if dialogs.CompanyEditDialog(win.db, win).exec():
        win.refresh_header()


def open_sale_invoice(win):
    """Sale invoices open as separate windows: minimize one and start the next bill meanwhile."""
    dlg = SaleInvoiceDialog(win.db, None)
    dlg.setAttribute(Qt.WA_DeleteOnClose, False)
    wins = win.__dict__.setdefault("invoice_windows", [])
    wins.append(dlg)

    def _gone(*_):
        if dlg in wins:
            wins.remove(dlg)
        dlg.deleteLater()
    dlg.finished.connect(_gone)
    dlg.show()
    dlg.raise_()
    dlg.activateWindow()


def _change_password(win):
    dialogs.ChangePasswordDialog(win.db, win).exec()


MODULES = {
    "categories": lambda win: CategoriesDialog(win.db, win).exec(),
    "reset_db": lambda win: ResetDialog(win).exec(),
    "backup": lambda win: BackupDialog(win.db, win).exec(),
    "restore": restore_dialog,
    "sale_return": lambda win: ReturnDialog(win.db, "sale", win).exec(),
    "purchase_return": lambda win: ReturnDialog(win.db, "purchase", win).exec(),
    "cash_book": open_cash_book,
    "balance_sheet": open_balance_sheet,
    "vouchers": open_vouchers,
    "stock_purchase": lambda win: StockPurchaseDialog(win.db, win).exec(),
    "cash_received": lambda win: CashRecoveryDialog(win.db, win).exec(),
    "pay_supplier": lambda win: PaymentDialog(win.db, "pay_supplier", win).exec(),
    "pay_customer": lambda win: PaymentDialog(win.db, "pay_customer", win).exec(),
    "expenses": lambda win: PaymentDialog(win.db, "expense", win).exec(),
    "sale_invoice": open_sale_invoice,
    "customers": lambda win: PartiesWindow(win.db, "customer", win).exec(),
    "suppliers": lambda win: PartiesWindow(win.db, "supplier", win).exec(),
    "products": lambda win: ProductsWindow(win.db, win).exec(),
    "company_edit": _company_edit,
    "about": lambda win: dialogs.show_about(win, win.db),
    "change_password": _change_password,
}


MODULES.update(SCREENS)


def open_module(win, key: str, label: str):
    handler = MODULES.get(key)
    if handler:
        handler(win)
    else:
        QMessageBox.information(win, APP_NAME, f"'{label}' will be available in the next build step.")
