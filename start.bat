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

if not exist .venv\Scripts\python.exe (
  echo ^>^> Erstelle virtuelle Umgebung ^(einmalig^) ...
  python -m venv .venv
  if errorlevel 1 (
    echo.
    echo FEHLER: Python wurde nicht gefunden. Bitte Python 3.11+ von python.org
    echo installieren und dabei "Add python.exe to PATH" anhaken.
    pause
    exit /b 1
  )
)

REM Pruefung auf uvicorn.exe statt nur auf den .venv-Ordner: so wird eine
REM frueher abgebrochene Installation automatisch repariert.
if not exist .venv\Scripts\uvicorn.exe (
  echo ^>^> Installiere Abhaengigkeiten ^(einmalig, 1-2 Minuten^) ...
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
)

echo ^>^> Starte Wissens-Chatbot auf http://localhost:8000
.venv\Scripts\python -m uvicorn app.main:app --port 8000
pause
