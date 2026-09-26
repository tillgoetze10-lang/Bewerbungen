"""Technische Einstellungen aus config.yaml (optional).

Suchprofile und Quellen-Schalter werden im UI unter "Einstellungen" gepflegt
(Datenbank). config.yaml wird nur noch fuer technische Dinge gebraucht und
beim allerersten Start einmal als Vorlage fuer die Suchprofile gelesen.
"""

import os

import yaml

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config.yaml")
EXAMPLE_CONFIG_PATH = os.path.join(BASE_DIR, "config.example.yaml")

DEFAULTS = {
    "search_profiles": [],
    "sources": {},
    "serpapi_key": "",
    "fetch_interval_minutes": 60,
    "fetch_on_startup": True,
    "fetch_job_details": True,
    "notify_new_top": True,
    "follow_up_days": 14,
    "http_timeout_seconds": 15,
    "user_agent": "Mozilla/5.0 (compatible; PersoenlicherJobBot/1.0; privater Gebrauch)",
}


def load_config():
    path = CONFIG_PATH if os.path.exists(CONFIG_PATH) else EXAMPLE_CONFIG_PATH
    data = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError):
        data = {}
    merged = dict(DEFAULTS)
    if isinstance(data, dict):
        merged.update({k: v for k, v in data.items() if v is not None})
    return merged
