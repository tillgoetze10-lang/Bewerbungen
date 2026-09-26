#!/bin/bash
# Doppelklick-Start fuer macOS. Holt bei jedem Start den neuesten Stand,
# richtet beim ersten Mal alles ein und oeffnet danach den Browser.
cd "$(dirname "$0")"

if [ -d ".git" ]; then
  echo "Suche nach Updates ..."
  if git pull --ff-only; then
    echo "Auf dem neuesten Stand."
  else
    echo "Update nicht möglich (offline?) – starte mit dem vorhandenen Stand."
  fi
  echo ""
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 fehlt. Bitte von https://www.python.org/downloads/ installieren und erneut starten."
  read -r -p "Enter zum Schließen ..."
  exit 1
fi

set -e

if [ ! -d ".venv" ]; then
  echo "Erstmaliges Setup: virtuelle Umgebung wird angelegt ..."
  python3 -m venv .venv
fi

source .venv/bin/activate

echo "Prüfe Abhängigkeiten ..."
pip install -q --disable-pip-version-check -r requirements.txt

if [ ! -f "config.yaml" ]; then
  cp config.example.yaml config.yaml
fi

python run.py
