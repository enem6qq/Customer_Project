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

if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
  echo "FEHLER: Es wird Python 3.11 oder neuer benötigt. Gefunden: $(python3 --version 2>&1)"
  exit 1
fi

# Falls die virtuelle Umgebung mit einem zu alten Python angelegt wurde:
# automatisch entfernen und neu aufbauen.
if [ -x .venv/bin/python ] && ! .venv/bin/python -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
  echo ">> Vorhandene Umgebung nutzt ein zu altes Python – baue neu auf ..."
  rm -rf .venv
fi

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
