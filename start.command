#!/bin/bash
# Doppelklick-Start fuer macOS: im Finder auf start.command doppelklicken.
# Beim allerersten Mal richtet das Skript automatisch alles ein
# (virtuelle Umgebung, Abhaengigkeiten, config.yaml) und startet danach
# die App - der Browser oeffnet sich von selbst.
set -e
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "Erstmaliges Setup: virtuelle Umgebung wird angelegt..."
  python3 -m venv .venv
fi

source .venv/bin/activate

echo "Pruefe/installiere Abhaengigkeiten..."
pip install -q -r requirements.txt

if [ ! -f "config.yaml" ]; then
  echo "Lege config.yaml aus config.example.yaml an (bitte spaeter nach deinen Wuenschen anpassen)..."
  cp config.example.yaml config.yaml
fi

echo ""
echo "Starte Bewerbungs-Board - der Browser oeffnet sich gleich automatisch."
echo "Zum Beenden dieses Fenster schliessen oder Strg+C druecken."
echo ""

python run.py
