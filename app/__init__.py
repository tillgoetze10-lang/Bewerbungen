import os
import secrets
from datetime import timezone
from urllib.parse import urlparse

from flask import Flask, abort, request

from .config import BASE_DIR
from .models import db

DATA_DIR = os.path.join(BASE_DIR, "data")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
DB_PATH = os.path.join(DATA_DIR, "app.db")
SECRET_PATH = os.path.join(DATA_DIR, "secret_key")


def _secret_key():
    if os.environ.get("SECRET_KEY"):
        return os.environ["SECRET_KEY"]
    if os.path.exists(SECRET_PATH):
        with open(SECRET_PATH, "r", encoding="utf-8") as f:
            key = f.read().strip()
            if key:
                return key
    key = secrets.token_hex(32)
    with open(SECRET_PATH, "w", encoding="utf-8") as f:
        f.write(key)
    return key


def create_app(database_uri=None):
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = database_uri or f"sqlite:///{DB_PATH}"
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"connect_args": {"timeout": 30}}
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["UPLOAD_DIR"] = UPLOAD_DIR
    app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024
    app.secret_key = _secret_key()

    db.init_app(app)

    from .db_setup import setup_database

    with app.app_context():
        setup_database()

    from .routes import bp

    app.register_blueprint(bp)

    @app.before_request
    def block_cross_site_posts():
        # Die App laeuft lokal ohne Login. Ohne diese Pruefung koennte jede
        # fremde Webseite im Browser unbemerkt Formulare an 127.0.0.1 schicken
        # (Jobs loeschen, Dokumente entfernen ...).
        if request.method in ("POST", "PUT", "DELETE"):
            origin = request.headers.get("Origin") or request.headers.get("Referer")
            if origin and origin != "null" and urlparse(origin).netloc != request.host:
                abort(403)

    @app.context_processor
    def inject_globals():
        from .fetch_runner import snapshot
        from .status import broken_source_names

        try:
            broken = broken_source_names()
        except Exception:
            broken = []
        return {"broken_sources": broken, "fetch_state": snapshot()}

    @app.template_filter("localtime")
    def localtime(value, fmt="%d.%m.%Y %H:%M"):
        if not value:
            return ""
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone().strftime(fmt)

    @app.template_filter("source_label")
    def source_label_filter(value):
        from .scrapers import source_label

        return source_label(value or "")

    return app
