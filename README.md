# Business Manager (offline, Windows)
Python 3.11+ / PySide6 / encrypted SQLite. Data folder: D:\BusinessManagerData (falls back to C:\).

## Setup
    pip install -r requirements.txt
    python -m pytest          # core accounting tests

## Progress
- [x] Step 1: structure, encrypted DB, schema, auth (register/login/lockout/change password),
      sale/purchase/returns/payments/reports logic, 17 passing tests
- [x] Step 2: registration + login screens (PySide6) - run with `python main.py`
- [ ] Step 3: home screen + menus
- [ ] Step 4: master forms, sale invoice, purchase, payments, reports UI
- [ ] Step 5: invoice PDF (A4 + 80mm), backup/restore, PyInstaller build
