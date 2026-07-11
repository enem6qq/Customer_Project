@echo off
REM Startet den Wissens-Chatbot lokal (Windows).
REM
REM   start.bat            -> Team-Modus (Demo-Benutzer, siehe README)
REM   start.bat privat     -> Privat-Modus: kein Login, eigene Dokumente
REM
REM Eigenen Dokumentenordner verwenden (vorher setzen):
REM   set DOCUMENTS_PATH=C:\Users\IchSelbst\Dokumente
REM
REM WICHTIG: Das Projekt in einen KURZEN Pfad legen (z. B. C:\Projekte\chatbot),
REM sonst kann die Installation an der Windows-Pfadlaengengrenze scheitern.
cd /d "%~dp0"

if "%1"=="privat" (
  set "TENANT_CONFIG=%cd%\config\tenant.privat.yaml"
  echo ^>^> Privat-Modus ^(kein Login^)
)

cd backend

REM Python suchen: der py-Launcher waehlt automatisch die neueste Version,
REM falls mehrere installiert sind (z. B. altes 3.8 + neues 3.12).
set "PYTHON=python"
where py >nul 2>nul && set "PYTHON=py -3"

%PYTHON% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
if errorlevel 1 (
  echo.
  echo FEHLER: Es wird Python 3.11 oder neuer benoetigt. Gefunden wurde:
  %PYTHON% --version 2>nul || echo   kein Python im PATH
  echo Bitte von https://www.python.org/downloads/ installieren und dabei
  echo "Add python.exe to PATH" anhaken. Danach ein NEUES Terminal oeffnen
  echo und start.bat erneut ausfuehren.
  pause
  exit /b 1
)

REM Falls die virtuelle Umgebung mit einem zu alten Python angelegt wurde:
REM automatisch entfernen und neu aufbauen.
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
  if errorlevel 1 (
    echo ^>^> Vorhandene Umgebung nutzt ein zu altes Python – baue neu auf ...
    rmdir /s /q .venv
  )
)

if not exist .venv\Scripts\python.exe (
  echo ^>^> Erstelle virtuelle Umgebung ^(einmalig^) ...
  %PYTHON% -m venv .venv
  if errorlevel 1 (
    echo.
    echo FEHLER: Die virtuelle Umgebung konnte nicht erstellt werden.
    pause
    exit /b 1
  )
)

REM Installieren, wenn (a) noch nie installiert oder (b) requirements.txt
REM sich seit der letzten Installation geaendert hat (req.stamp-Vergleich).
REM So kommen neue Abhaengigkeiten nach einem Update automatisch an.
fc /b requirements.txt .venv\req.stamp >nul 2>nul
if errorlevel 1 (
  echo ^>^> Installiere/aktualisiere Abhaengigkeiten ^(1-2 Minuten^) ...
  .venv\Scripts\python -m pip install --quiet -r requirements.txt
  if errorlevel 1 (
    echo.
    echo FEHLER bei der Installation. Haeufigste Ursache: Der Projektordner
    echo liegt in einem zu langen Pfad. Bitte das Projekt z. B. nach
    echo C:\Projekte\chatbot verschieben und start.bat erneut ausfuehren.
    echo Alternativ Windows Long Paths aktivieren:
    echo https://pip.pypa.io/warnings/enable-long-paths
    pause
    exit /b 1
  )
  copy /y requirements.txt .venv\req.stamp >nul
)

echo ^>^> Starte Wissens-Chatbot auf http://localhost:8000
.venv\Scripts\python -m uvicorn app.main:app --port 8000
pause
