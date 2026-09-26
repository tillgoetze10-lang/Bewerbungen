import hashlib
from datetime import date, datetime, timedelta, timezone

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def utcnow():
    return datetime.now(timezone.utc)


# Reihenfolge = Spaltenreihenfolge im Board (links -> rechts).
STATUS_FLOW = [
    ("neu", "Neu"),
    ("interessant", "Interessant"),
    ("vorbereitung", "In Vorbereitung"),
    ("beworben", "Beworben"),
    ("rueckmeldung", "Rückmeldung erhalten"),
]
STATUS_ARCHIVIERT = "archiviert"
STATUS_KEYS = [key for key, _ in STATUS_FLOW]
STATUS_LABELS = dict(STATUS_FLOW)
STATUS_LABELS[STATUS_ARCHIVIERT] = "Archiv / Nicht interessant"


def make_external_id(url: str) -> str:
    return hashlib.sha256(url.strip().lower().encode("utf-8")).hexdigest()


def is_web_url(value) -> bool:
    return isinstance(value, str) and value.strip().lower().startswith(("http://", "https://"))


class Job(db.Model):
    __tablename__ = "jobs"

    id = db.Column(db.Integer, primary_key=True)
    external_id = db.Column(db.String(64), unique=True, nullable=False, index=True)
    title = db.Column(db.String(300), nullable=False)
    company = db.Column(db.String(200), default="")
    location = db.Column(db.String(200), default="")
    url = db.Column(db.String(1000), nullable=False)
    source = db.Column(db.String(100), nullable=False)
    source_ref = db.Column(db.String(200), default="")  # z.B. Referenznummer der Arbeitsagentur
    salary = db.Column(db.String(200), default="")
    description = db.Column(db.Text, default="")
    posted_at = db.Column(db.String(50), default="")
    fetched_at = db.Column(db.DateTime, default=utcnow)
    status = db.Column(db.String(30), default="neu", index=True)
    notes = db.Column(db.Text, default="")
    cover_letter = db.Column(db.Text, default="")
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    # Automatische Ersteinschaetzung (app/matching.py) - nur eine Empfehlung.
    match_score = db.Column(db.Float, default=0.0, index=True)
    match_label = db.Column(db.String(20), default="pruefen")
    match_reason = db.Column(db.Text, default="")

    # Automatisch extrahierte Zusatzinfos (app/extraction.py) - Best-Effort,
    # daher mit Confidence-Einstufung und im UI korrigierbar.
    tasks = db.Column(db.Text, default="")
    contact_name = db.Column(db.String(200), default="")
    contact_salutation = db.Column(db.String(10), default="")  # "Frau" | "Herr" | ""
    contact_email = db.Column(db.String(200), default="")
    contact_phone = db.Column(db.String(100), default="")
    company_website = db.Column(db.String(500), default="")
    requirements = db.Column(db.Text, default="")
    application_documents = db.Column(db.Text, default="")
    extraction_confidence = db.Column(db.String(20), default="unsicher")
    extraction_missing = db.Column(db.Text, default="")

    # Bewerbungs-Fahrplan
    deadline = db.Column(db.Date)  # Bewerbungsfrist laut Anzeige
    docs_done = db.Column(db.Text, default="")  # abgehakte Unterlagen, komma-getrennt
    applied_at = db.Column(db.Date)
    follow_up_at = db.Column(db.Date)

    documents = db.relationship("JobDocument", backref="job", cascade="all, delete-orphan", lazy="dynamic")

    def status_label(self):
        return STATUS_LABELS.get(self.status, self.status)

    def match_label_text(self):
        from .matching import LABEL_TEXT

        return LABEL_TEXT.get(self.match_label, self.match_label or "Prüfen")

    def match_percent(self):
        return int(round((self.match_score or 0) * 100))

    def has_web_url(self):
        return is_web_url(self.url)

    def has_company_website(self):
        return is_web_url(self.company_website)

    def document_checklist(self):
        return [d.strip() for d in (self.application_documents or "").split(",") if d.strip()]

    def docs_done_list(self):
        return [d.strip() for d in (self.docs_done or "").split(",") if d.strip()]

    def docs_progress(self):
        required = self.document_checklist()
        done = [d for d in required if d in self.docs_done_list()]
        return len(done), len(required)

    def follow_up_due(self, today=None):
        today = today or date.today()
        return bool(self.follow_up_at and self.follow_up_at <= today and self.status == "beworben")

    def deadline_state(self, today=None):
        """"" | "bald" (<= 7 Tage) | "abgelaufen" """
        if not self.deadline or self.status not in ("neu", "interessant", "vorbereitung"):
            return ""
        today = today or date.today()
        if self.deadline < today:
            return "abgelaufen"
        return "bald" if self.deadline - today <= timedelta(days=7) else ""

    def mark_applied(self, today=None, follow_up_days=14):
        today = today or date.today()
        if not self.applied_at:
            self.applied_at = today
        if not self.follow_up_at:
            self.follow_up_at = self.applied_at + timedelta(days=follow_up_days)

    def missing_fields_labels(self):
        from .extraction import FIELD_LABELS

        keys = [k for k in (self.extraction_missing or "").split(",") if k]
        return [FIELD_LABELS.get(k, k) for k in keys]

    def extraction_confidence_text(self):
        from .extraction import CONFIDENCE_LABELS

        return CONFIDENCE_LABELS.get(self.extraction_confidence, self.extraction_confidence or "")


class Document(db.Model):
    """Zentrale Dokumentenbibliothek (Lebenslauf, Anschreiben-Vorlagen, Zeugnisse, ...)."""

    __tablename__ = "documents"

    id = db.Column(db.Integer, primary_key=True)
    doc_type = db.Column(db.String(50), nullable=False, default="sonstiges")
    title = db.Column(db.String(200), nullable=False)
    filename = db.Column(db.String(300), nullable=False)
    stored_path = db.Column(db.String(500), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=utcnow)


class JobDocument(db.Model):
    __tablename__ = "job_documents"

    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey("jobs.id"), nullable=False)
    document_id = db.Column(db.Integer, db.ForeignKey("documents.id"), nullable=False)

    document = db.relationship("Document")


class CompanySource(db.Model):
    """Hinterlegte Firmen-Karriereseiten, die bei jedem Suchlauf mit durchsucht werden."""

    __tablename__ = "company_sources"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    career_url = db.Column(db.String(1000), nullable=False)
    active = db.Column(db.Boolean, default=True)
    added_at = db.Column(db.DateTime, default=utcnow)
    last_result = db.Column(db.String(300), default="")

    @property
    def source_key(self):
        return f"firma:{self.name}"


class SearchProfile(db.Model):
    """Suchbegriff + Ort, im UI unter "Einstellungen" pflegbar (kein YAML noetig)."""

    __tablename__ = "search_profiles"

    id = db.Column(db.Integer, primary_key=True)
    keywords = db.Column(db.String(200), nullable=False)
    location = db.Column(db.String(200), default="")
    radius_km = db.Column(db.Integer, default=25)
    active = db.Column(db.Boolean, default=True)

    def as_dict(self):
        return {"keywords": self.keywords, "location": self.location or "", "radius_km": self.radius_km or 25}


class SourceSetting(db.Model):
    """An/Aus-Schalter je Jobportal, im UI pflegbar."""

    __tablename__ = "source_settings"

    name = db.Column(db.String(50), primary_key=True)
    enabled = db.Column(db.Boolean, default=True)


class AppSetting(db.Model):
    """Frei belegbare Einstellungen, v.a. API-Schluessel (Adzuna, Jooble, SerpApi)."""

    __tablename__ = "app_settings"

    key = db.Column(db.String(80), primary_key=True)
    value = db.Column(db.Text, default="")

    @staticmethod
    def as_dict():
        return {s.key: s.value for s in AppSetting.query.all() if s.value}


class CoverLetterTemplate(db.Model):
    """Anschreiben-Vorlagen mit Platzhaltern (siehe app/letters.py)."""

    __tablename__ = "cover_letter_templates"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    body = db.Column(db.Text, default="")
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)


class ScraperRun(db.Model):
    """Protokoll jedes Quellen-Abrufs - treibt die Status-Seite und den Warn-Banner.

    kind: "ok" | "blocked" (Seite laesst automatische Abfragen nicht zu - kein
    Bug) | "config" (Einstellung fehlt) | "offline" (kein Internet) |
    "error" (echter Fehler, den Claude beheben kann)
    """

    __tablename__ = "scraper_runs"

    id = db.Column(db.Integer, primary_key=True)
    ran_at = db.Column(db.DateTime, default=utcnow, index=True)
    source = db.Column(db.String(100), nullable=False, index=True)
    ok = db.Column(db.Boolean, default=True)
    kind = db.Column(db.String(20), default="ok")
    message = db.Column(db.Text, default="")
    new_jobs = db.Column(db.Integer, default=0)
