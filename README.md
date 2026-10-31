# Business Manager (offline, Windows)
Python 3.11+ / PySide6 / encrypted SQLite. Data folder: D:\BusinessManagerData (falls back to C:\).

## Setup
    pip install -r requirements.txt
    python -m pytest          # core accounting tests

## Progress
- [x] Step 1: structure, encrypted DB, schema, auth (register/login/lockout/change password),
      sale/purchase/returns/payments/reports logic, 17 passing tests
- [x] Step 2: registration + login screens (PySide6) - run with `python main.py`
- [x] Step 3: home screen + 6 menus (About, Change Password, Company Edit working; rest are placeholders)
- [x] Step 4 done: masters, Sale Invoice (+PDF), Stock Purchase, payments/receipts/expenses, returns, Cash Book, Balance Sheet, Vouchers (report engine with Excel/CSV/PDF)
- [ ] Step 5: remaining reports, Invoice Print (view/edit/cancel), Sale Summary, Backup/Restore, .exe build, user manual
- [ ] Step 5: invoice PDF (A4 + 80mm), backup/restore, PyInstaller build
