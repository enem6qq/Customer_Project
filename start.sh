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
if [ ! -d .venv ]; then
  echo ">> Erstelle virtuelle Umgebung und installiere Abhängigkeiten (einmalig) ..."
  python3 -m venv .venv
  .venv/bin/pip install --quiet --upgrade pip
  .venv/bin/pip install --quiet -r requirements.txt
fi

echo ">> Starte Wissens-Chatbot auf http://localhost:8000"
exec .venv/bin/uvicorn app.main:app --port 8000
