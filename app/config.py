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
    "http_timeout_seconds": 15,
    "user_agent": "Mozilla/5.0 (compatible; PersoenlicherJobBot/1.0; +privater Gebrauch)",
}


def load_config():
    path = CONFIG_PATH if os.path.exists(CONFIG_PATH) else EXAMPLE_CONFIG_PATH
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    merged = dict(DEFAULTS)
    merged.update(data)
    return merged


def source_enabled(config, name):
    return bool(config.get("sources", {}).get(name, {}).get("enabled", False))
