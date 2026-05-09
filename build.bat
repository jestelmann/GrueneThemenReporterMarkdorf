@echo off
setlocal

cd /d "%~dp0"

set "PYTHON_EXE=.venv\Scripts\python.exe"
set "WORK_PATH=%TEMP%\GrueneThemenResearcher_pyi_work"
set "SPEC_PATH=."
set "DIST_PATH=dist"

if not exist "%PYTHON_EXE%" (
  echo [ERROR] Python in .venv nicht gefunden: %PYTHON_EXE%
  echo [HINWEIS] Lege zuerst eine virtuelle Umgebung im Projekt an.
  exit /b 1
)

echo [INFO] Verwende Python: %PYTHON_EXE%
"%PYTHON_EXE%" -m pip show pyinstaller >nul 2>&1
if errorlevel 1 (
  echo [INFO] PyInstaller wird installiert...
  "%PYTHON_EXE%" -m pip install pyinstaller
  if errorlevel 1 (
    echo [ERROR] Installation von PyInstaller fehlgeschlagen.
    exit /b 1
  )
)

echo [INFO] Starte EXE-Build...
"%PYTHON_EXE%" -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --workpath "%WORK_PATH%" ^
  --specpath "%SPEC_PATH%" ^
  --distpath "%DIST_PATH%" ^
  --windowed ^
  --onefile ^
  --name GrueneThemenResearcher ^
  --exclude-module PyQt5 ^
  --collect-data crewai ^
  --add-data "assets/gruene_icon.svg;assets" ^
  GrueneThemenResearcher.py

if errorlevel 1 (
  echo [ERROR] Build fehlgeschlagen.
  exit /b 1
)

echo [OK] Build erfolgreich.
echo [OK] EXE: dist\GrueneThemenResearcher.exe
echo [HINWEIS] Starte nur die EXE aus dem dist-Ordner, nicht aus build.

exit /b 0
