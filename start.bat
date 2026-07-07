@echo off
REM Startet den Wissens-Chatbot lokal (Windows).
REM
REM   start.bat            -> Team-Modus (Demo-Benutzer, siehe README)
REM   start.bat privat     -> Privat-Modus: kein Login, eigene Dokumente
REM
REM Eigenen Dokumentenordner verwenden (vorher setzen):
REM   set DOCUMENTS_PATH=C:\Users\IchSelbst\Dokumente
cd /d "%~dp0"

if "%1"=="privat" (
  set "TENANT_CONFIG=%cd%\config\tenant.privat.yaml"
  echo ^>^> Privat-Modus ^(kein Login^)
)

cd backend
if not exist .venv (
  echo ^>^> Erstelle virtuelle Umgebung und installiere Abhaengigkeiten ^(einmalig^) ...
  python -m venv .venv
  .venv\Scripts\pip install --quiet --upgrade pip
  .venv\Scripts\pip install --quiet -r requirements.txt
)

echo ^>^> Starte Wissens-Chatbot auf http://localhost:8000
.venv\Scripts\uvicorn app.main:app --port 8000
