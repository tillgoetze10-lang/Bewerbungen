#!/bin/bash
# Doppelklick-Start fuer macOS: im Finder auf start.command doppelklicken.
# Holt bei jedem Start automatisch den neuesten Stand aus Git (Auto-Update),
# richtet beim allerersten Mal alles ein (venv, Abhaengigkeiten, config.yaml)
# und startet danach die App - der Browser oeffnet sich von selbst.
cd "$(dirname "$0")"

if [ -d ".git" ]; then
  echo "Suche nach Updates..."
  if git pull --ff-only 2>&1; then
    echo "Auf dem neuesten Stand."
  else
    echo "Update fehlgeschlagen (z.B. offline oder lokale Aenderungen im Weg) -"
    echo "starte mit dem vorhandenen Stand weiter."
  fi
  echo ""
fi

set -e

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
