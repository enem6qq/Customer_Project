#!/usr/bin/env bash
# Startet den Wissens-Chatbot lokal (Linux/macOS).
#
#   ./start.sh              -> Team-Modus (Demo-Benutzer, siehe README)
#   ./start.sh privat       -> Privat-Modus: kein Login, eigene Dokumente
#
# Eigenen Dokumentenordner verwenden:
#   DOCUMENTS_PATH="$HOME/Dokumente" ./start.sh privat
set -euo pipefail
cd "$(dirname "$0")"

if [ "${1:-}" = "privat" ]; then
  export TENANT_CONFIG="$(pwd)/config/tenant.privat.yaml"
  echo ">> Privat-Modus (kein Login)"
fi

cd backend

if [ ! -x .venv/bin/python ]; then
  echo ">> Erstelle virtuelle Umgebung (einmalig) ..."
  python3 -m venv .venv
fi

# Prüfung auf uvicorn statt nur auf den .venv-Ordner: so wird eine früher
# abgebrochene Installation automatisch repariert.
if [ ! -x .venv/bin/uvicorn ]; then
  echo ">> Installiere Abhängigkeiten (einmalig, 1-2 Minuten) ..."
  .venv/bin/python -m pip install --quiet -r requirements.txt
fi

echo ">> Starte Wissens-Chatbot auf http://localhost:8000"
exec .venv/bin/python -m uvicorn app.main:app --port 8000
