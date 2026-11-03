"""Home buttons and menu bar layout as plain data (no Qt), so it can be tested.

Each entry is (label, key). `key` is looked up in MODULES (app/ui/modules.py);
keys with no registered screen yet show a "coming soon" message.
"""

HOME_BUTTONS = [
    ("Sale Invoice", "sale_invoice"),
    ("Stock Purchase", "stock_purchase"),
    ("Cash Recovery", "cash_received"),
    ("Stock Report", "stock_position"),
    ("Outstanding / Baqayajat", "outstanding"),
    ("Sale Summary", "sale_summary"),
    ("Profit Loss Report", "profit_loss"),
]

MENUS = [
    ("New Account", [
        ("Company Information Edit", "company_edit"),
        ("Supplier", "suppliers"),
        ("Customers", "customers"),
        ("Products", "products"),
        ("Categories", "categories"),
        ("Import from Excel", "import_data"),
    ]),
    ("Sale/Purchase", [
        ("Sale Summary", "sale_summary"),
        ("Sale Return", "sale_return"),
        ("Products Purchase", "stock_purchase"),
        ("Purchase Return", "purchase_return"),
        ("Installments (Qist)", "qist"),
        ("Repair Jobs", "repairs"),
    ]),
    ("Payments/Receipts", [
        ("Cash Received from Customer", "cash_received"),
        ("Expenses", "expenses"),
        ("Payment to Supplier", "pay_supplier"),
        ("Payment to Customer", "pay_customer"),
    ]),
    ("Account Transactions", [
        ("Cash Book", "cash_book"),
        ("Balance Sheet", "balance_sheet"),
        ("Vouchers", "vouchers"),
    ]),
    ("Reports", [
        ("Customer Transactions", "customer_transactions"),
        ("Cash Received", "cash_received_report"),
        ("Profit Loss Report", "profit_loss"),
        ("Invoice Wise Sale Summary", "invoice_wise"),
        ("Stock Position", "stock_position"),
        ("Products Ledger", "product_ledger"),
        ("All Customer Balance", "all_balances"),
        ("Invoice Print", "invoice_print"),
        ("Products", "products_report"),
        ("IMEI Search / History", "imei_search"),
        ("Daily Closing", "daily_closing"),
        ("Qist Due List", "qist_due"),
        ("Price List", "price_list"),
        ("Barcode / Price Labels", "labels"),
    ]),
    ("Utilities", [
        ("Backup", "backup"),
        ("Restore Backup", "restore"),
        ("About", "about"),
        ("Change Password / Username", "change_password"),
        ("Staff Accounts", "users"),
        ("Audit Log", "audit_log"),
        ("Printer Settings", "printer_settings"),
        ("Reset Database", "reset_db"),
    ]),
]

# Keyboard shortcuts (key -> shortcut)
SHORTCUTS = {"sale_invoice": "F2", "stock_purchase": "F3", "cash_received": "F4"}

# Screens that are built (everything else shows a placeholder). Updated as steps finish.
IMPLEMENTED = {"company_edit", "about", "change_password", "customers", "suppliers", "products", "sale_invoice",
               "stock_purchase", "cash_received", "pay_supplier", "pay_customer", "expenses",
               "cash_book", "balance_sheet", "vouchers", "sale_return", "purchase_return",
               "customer_transactions", "cash_received_report", "profit_loss", "invoice_wise", "stock_position",
               "product_ledger", "all_balances", "products_report", "outstanding", "sale_summary", "invoice_print",
               "backup", "restore", "categories", "reset_db", "printer_settings", "imei_search", "daily_closing", "users", "audit_log", "import_data", "qist", "repairs", "qist_due", "price_list", "labels"}


def all_keys():
    keys = [k for _, k in HOME_BUTTONS]
    for _, items in MENUS:
        keys += [k for _, k in items]
    return keys
