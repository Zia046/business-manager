@echo off
REM ===== Build BusinessManager.exe (run this on Windows, inside the project folder) =====
REM 1) one-time:  python -m venv venv  &&  venv\Scripts\activate  &&  pip install -r requirements-dev.txt
REM 2) then just double-click this file (or run it from the activated venv).

echo Running tests first...
python -m pytest -q
if errorlevel 1 (
  echo Tests failed - fix them before building.
  pause
  exit /b 1
)

pyinstaller --noconfirm --clean --onedir --windowed ^
  --name BusinessManager ^
  --icon assets\app.ico ^
  --hidden-import rapidfuzz ^
  --hidden-import arabic_reshaper ^
  --hidden-import bidi ^
  --hidden-import openpyxl ^
  main.py

if errorlevel 1 (
  echo Build failed.
  pause
  exit /b 1
)
echo.
echo Done. Your program is:  dist\BusinessManager\BusinessManager.exe
echo Installer: open installer.iss with Inno Setup and press Compile (creates installer_output\BusinessManager-Setup.exe).
pause
