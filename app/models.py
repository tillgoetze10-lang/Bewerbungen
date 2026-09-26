import hashlib
from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# Reihenfolge = Spaltenreihenfolge im Scrum-Board (links -> rechts).
STATUS_FLOW = [
    ("neu", "Neu"),
    ("interessant", "Interessant"),
    ("vorbereitung", "In Vorbereitung"),
    ("beworben", "Beworben"),
    ("rueckmeldung", "Rueckmeldung erhalten"),
]
STATUS_ARCHIVIERT = "archiviert"
STATUS_KEYS = [key for key, _ in STATUS_FLOW]
STATUS_LABELS = dict(STATUS_FLOW)
STATUS_LABELS[STATUS_ARCHIVIERT] = "Archiv / Nicht interessant"


def make_external_id(url: str) -> str:
    return hashlib.sha256(url.strip().lower().encode("utf-8")).hexdigest()


class Job(db.Model):
    __tablename__ = "jobs"

    id = db.Column(db.Integer, primary_key=True)
    external_id = db.Column(db.String(64), unique=True, nullable=False, index=True)
    title = db.Column(db.String(300), nullable=False)
    company = db.Column(db.String(200))
    location = db.Column(db.String(200))
    url = db.Column(db.String(1000), nullable=False)
    source = db.Column(db.String(50), nullable=False)
    salary = db.Column(db.String(200))
    description = db.Column(db.Text)
    posted_at = db.Column(db.String(50))
    fetched_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    status = db.Column(db.String(30), default="neu", index=True)
    notes = db.Column(db.Text, default="")
    cover_letter = db.Column(db.Text, default="")
    updated_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )

    # Automatische Ersteinschaetzung (siehe app/matching.py) - nur eine Empfehlung,
    # loescht/versteckt nichts von selbst.
    match_score = db.Column(db.Float, default=0.0, index=True)
    match_label = db.Column(db.String(20), default="pruefen")
    match_reason = db.Column(db.Text, default="")

    # Automatisch extrahierte Zusatzinfos (siehe app/extraction.py) - Best-Effort,
    # daher immer mit Confidence-Einstufung und von Hand korrigierbar im UI.
    contact_name = db.Column(db.String(200), default="")
    contact_email = db.Column(db.String(200), default="")
    contact_phone = db.Column(db.String(100), default="")
    company_website = db.Column(db.String(500), default="")
    requirements = db.Column(db.Text, default="")
    application_documents = db.Column(db.Text, default="")
    extraction_confidence = db.Column(db.String(20), default="unsicher")
    extraction_missing = db.Column(db.Text, default="")  # komma-getrennte Feldnamen, fuer Anzeige "bitte pruefen"

    documents = db.relationship(
        "JobDocument", backref="job", cascade="all, delete-orphan", lazy="dynamic"
    )

    def status_label(self):
        return STATUS_LABELS.get(self.status, self.status)

    def match_label_text(self):
        from .matching import LABEL_TEXT

        return LABEL_TEXT.get(self.match_label, self.match_label)

    def missing_fields_labels(self):
        from .extraction import FIELD_LABELS

        keys = [k for k in (self.extraction_missing or "").split(",") if k]
        return [FIELD_LABELS.get(k, k) for k in keys]

    def extraction_confidence_text(self):
        from .extraction import CONFIDENCE_LABELS

        return CONFIDENCE_LABELS.get(self.extraction_confidence, self.extraction_confidence)


class Document(db.Model):
    """Zentrale Dokumentenbibliothek (Lebenslauf, Anschreiben-Vorlagen, Zeugnisse, ...)."""

    __tablename__ = "documents"

    id = db.Column(db.Integer, primary_key=True)
    doc_type = db.Column(db.String(50), nullable=False, default="sonstiges")
    title = db.Column(db.String(200), nullable=False)
    filename = db.Column(db.String(300), nullable=False)
    stored_path = db.Column(db.String(500), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class JobDocument(db.Model):
    """Verknuepfung: welches Dokument gehoert zu welcher Bewerbung."""

    __tablename__ = "job_documents"

    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey("jobs.id"), nullable=False)
    document_id = db.Column(db.Integer, db.ForeignKey("documents.id"), nullable=False)

    document = db.relationship("Document")


class CompanySource(db.Model):
    """Von dir hinterlegte Firmen-Karriereseiten, die beim Fetch-Lauf mit
    durchsucht werden (zusaetzlich zu den Jobportalen)."""

    __tablename__ = "company_sources"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    career_url = db.Column(db.String(1000), nullable=False)
    active = db.Column(db.Boolean, default=True)
    added_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_result = db.Column(db.String(300), default="")
