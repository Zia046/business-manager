# Business Manager (offline, Windows)

Sales, purchase, stock and accounts for a small shop. Python 3.11+, PySide6, encrypted local database.
No internet or server needed. Data folder: `D:\BusinessManagerData` (falls back to `C:\`).

## Run (development)
    python -m venv venv
    venv\Scripts\activate
    pip install -r requirements-dev.txt
    python -m pytest          # accounting + report tests
    python main.py

## Build the .exe
Easiest: push a tag (or use Actions > Build Windows exe > Run workflow) and GitHub builds `BusinessManager.exe` for you.
On your own PC: double-click `build_exe.bat` (runs the tests, then PyInstaller) -> `dist\BusinessManager.exe`.
Optional installer: open `installer.iss` in Inno Setup and Compile.

## User manual
See `USER_MANUAL.md` (Roman Urdu).

## Project layout
    main.py                 entry point (register -> login -> home)
    app/config.py           data folder rules
    app/db/                 encrypted database + schema
    app/services/           all business logic (auth, trading, payments, reports, backup)
    app/reports/            invoice/voucher/report PDFs, Excel/CSV export, report builders
    app/ui/                 PySide6 screens
    tests/                  automated tests for the accounting logic

## Status
Every menu item and home button is implemented. The business logic and reports are covered by automated
tests. The PySide6 screens were written without being run on a real Windows screen yet, so the first
run on your computer is the real test - report anything that looks or behaves wrongly.
