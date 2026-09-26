import os

from flask import Flask

from .config import BASE_DIR
from .models import db

DATA_DIR = os.path.join(BASE_DIR, "data")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
DB_PATH = os.path.join(DATA_DIR, "app.db")


def create_app():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DB_PATH}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["UPLOAD_DIR"] = UPLOAD_DIR
    app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024  # 25 MB je Upload

    db.init_app(app)

    with app.app_context():
        db.create_all()

    from .routes import bp

    app.register_blueprint(bp)

    @app.context_processor
    def inject_broken_sources():
        # Auf jeder Seite verfuegbar, damit der Warn-Banner in base.html
        # ueberall auftaucht, wenn eine Quelle gerade kaputt ist - nicht
        # nur auf /status.
        from .status import broken_source_names

        try:
            return {"broken_sources": broken_source_names()}
        except Exception:
            return {"broken_sources": []}

    return app
