import os
import subprocess
import uuid
from datetime import date, timedelta
from urllib.parse import urlparse

from flask import (
    Blueprint, current_app, flash, jsonify, redirect, render_template, request, send_from_directory, url_for,
)
from werkzeug.utils import secure_filename

from .company_suggestions import open_suggestions
from .config import BASE_DIR, load_config
from .extraction import empty_result
from .fetch_jobs import (
    DETAIL_FIELDS, apply_details, job_from_listing, load_details, merge_details_into_listing, missing_settings, runtime_config,
)
from .fetch_runner import snapshot, start_async
from .letters import PLACEHOLDERS, fill_template
from .matching import score_job
from .models import (
    STATUS_ARCHIVIERT, STATUS_FLOW, STATUS_KEYS, AppSetting, CompanySource, CoverLetterTemplate, Document, Job,
    JobDocument,
    ScraperRun, SearchProfile, SourceSetting, db, is_web_url, make_external_id,
)
from .scrapers import REGISTRY, SOURCE_HINTS, SOURCE_LABELS, source_label
from .scrapers.base import JobListing, ScraperError
from .scrapers.quick_add import fetch_from_url
from .status import latest_run_per_source, run_kind

bp = Blueprint("board", __name__)


def _safe_next(default_endpoint="board.board", **kwargs):
    target = request.form.get("next") or request.args.get("next") or ""
    if target.startswith("/") and not target.startswith("//"):
        return target
    referrer = request.referrer or ""
    if referrer and urlparse(referrer).netloc == request.host:
        return referrer
    return url_for(default_endpoint, **kwargs)


def _parse_date(value):
    try:
        return date.fromisoformat((value or "").strip()) if value else None
    except ValueError:
        return None


def _follow_up_days():
    try:
        return int(load_config().get("follow_up_days") or 14)
    except (TypeError, ValueError):
        return 14


def _set_status(job, new_status):
    job.status = new_status
    if new_status == "beworben":
        job.mark_applied(follow_up_days=_follow_up_days())


def _clean_web_url(value: str) -> str:
    value = (value or "").strip()
    if value and not is_web_url(value) and "." in value and " " not in value:
        value = "https://" + value
    return value if is_web_url(value) else ""


# ---------------------------------------------------------------- Board ----


@bp.route("/")
def board():
    columns = []
    for key, label in STATUS_FLOW:
        jobs = Job.query.filter_by(status=key).order_by(Job.match_score.desc(), Job.fetched_at.desc()).all()
        hidden = []
        if key == "neu":
            hidden = [j for j in jobs if j.match_label == "unpassend"]
            jobs = [j for j in jobs if j.match_label != "unpassend"]
        columns.append({"key": key, "label": label, "jobs": jobs, "hidden_jobs": hidden})
    archived_count = Job.query.filter_by(status=STATUS_ARCHIVIERT).count()
    follow_ups = [j for j in Job.query.filter_by(status="beworben").order_by(Job.follow_up_at).all() if j.follow_up_due()]
    return render_template("board.html", columns=columns, archived_count=archived_count, status_flow=STATUS_FLOW,
                           follow_ups=follow_ups)


@bp.route("/archiv")
def archive():
    jobs = Job.query.filter_by(status=STATUS_ARCHIVIERT).order_by(Job.updated_at.desc()).all()
    return render_template("archive.html", jobs=jobs)


@bp.route("/job/<int:job_id>/status", methods=["POST"])
def update_status(job_id):
    job = db.get_or_404(Job, job_id)
    data = request.get_json(silent=True) or request.form
    new_status = data.get("status")
    ok = new_status in STATUS_KEYS + [STATUS_ARCHIVIERT]
    if ok:
        _set_status(job, new_status)
        db.session.commit()
    if request.is_json:
        return jsonify({"ok": ok, "status": job.status})
    return redirect(_safe_next())


@bp.route("/job/<int:job_id>/delete", methods=["POST"])
def delete_job(job_id):
    """"Löschen" im Board = archivieren. Endgültig löschen geht im Archiv."""
    job = db.get_or_404(Job, job_id)
    job.status = STATUS_ARCHIVIERT
    db.session.commit()
    if request.is_json:
        return jsonify({"ok": True})
    return redirect(_safe_next())


@bp.route("/job/<int:job_id>/purge", methods=["POST"])
def purge_job(job_id):
    job = db.get_or_404(Job, job_id)
    JobDocument.query.filter_by(job_id=job.id).delete()
    db.session.delete(job)
    db.session.commit()
    flash("Job endgültig gelöscht.", "info")
    return redirect(url_for("board.archive"))


# ----------------------------------------------------------- Job-Detail ----


@bp.route("/job/<int:job_id>")
def job_detail(job_id):
    job = db.get_or_404(Job, job_id)
    linked_doc_ids = {jd.document_id for jd in job.documents}
    library_docs = Document.query.order_by(Document.doc_type, Document.title).all()
    templates = [{"id": t.id, "name": t.name, "text": fill_template(t.body, job)}
                 for t in CoverLetterTemplate.query.order_by(CoverLetterTemplate.name).all()]
    return render_template(
        "job_detail.html",
        job=job,
        letter_templates=templates,
        status_flow=STATUS_FLOW,
        archiv_status=STATUS_ARCHIVIERT,
        library_docs=library_docs,
        linked_docs=[d for d in library_docs if d.id in linked_doc_ids],
        linked_doc_ids=linked_doc_ids,
    )


@bp.route("/job/<int:job_id>/save", methods=["POST"])
def save_job(job_id):
    job = db.get_or_404(Job, job_id)
    for field in ("cover_letter", "notes", "tasks", "requirements", "application_documents",
                  "contact_name", "contact_email", "contact_phone"):
        if field in request.form:
            setattr(job, field, request.form.get(field, "").strip())
    if "company_website" in request.form:
        job.company_website = _clean_web_url(request.form.get("company_website", ""))
    if "contact_salutation" in request.form:
        salutation = request.form.get("contact_salutation", "")
        job.contact_salutation = salutation if salutation in ("Frau", "Herr") else ""
    if "docs_checklist_present" in request.form:
        done = [d for d in request.form.getlist("docs_done") if d in job.document_checklist()]
        job.docs_done = ", ".join(done)
    for field in ("deadline", "applied_at", "follow_up_at"):
        if field in request.form:
            setattr(job, field, _parse_date(request.form.get(field)))
    db.session.commit()
    flash("Gespeichert.", "success")
    return redirect(url_for("board.job_detail", job_id=job.id))


@bp.route("/job/<int:job_id>/reextract", methods=["POST"])
def reextract_job(job_id):
    """Anzeige erneut abrufen und Aufgaben/Kontakt/Unterlagen neu auslesen.
    Von Hand eingetragene Werte werden nur ueberschrieben, wenn neu etwas gefunden wurde."""
    job = db.get_or_404(Job, job_id)
    if not job.has_web_url():
        flash("Dieser Job hat keinen Link zur Anzeige – nichts zum Auslesen.", "info")
        return redirect(url_for("board.job_detail", job_id=job.id))

    listing = JobListing(title=job.title, url=job.url, source=job.source, ref=job.source_ref or "")
    details = load_details(listing, runtime_config())
    if not details:
        flash("Die Anzeige ließ sich nicht erneut abrufen (offline genommen, Bot-Schutz oder robots.txt).", "error")
        return redirect(url_for("board.job_detail", job_id=job.id))

    previous = {f: getattr(job, f) for f in DETAIL_FIELDS}
    apply_details(job, details)
    for field, old in previous.items():
        if not getattr(job, field) and old:
            setattr(job, field, old)
    db.session.commit()
    flash(f"Neu ausgelesen: {job.extraction_confidence_text()}.", "info")
    return redirect(url_for("board.job_detail", job_id=job.id))


@bp.route("/job/<int:job_id>/nachgefasst", methods=["POST"])
def followed_up(job_id):
    job = db.get_or_404(Job, job_id)
    today = date.today()
    line = f"{today:%d.%m.%Y}: nachgefasst."
    job.notes = f"{job.notes}\n{line}".strip() if job.notes else line
    job.follow_up_at = today + timedelta(days=_follow_up_days()) if request.form.get("again") else None
    db.session.commit()
    flash("Notiert. " + ("Nächste Erinnerung in zwei Wochen." if job.follow_up_at else "Erinnerung erledigt."), "success")
    return redirect(_safe_next())


@bp.route("/job/<int:job_id>/documents/link", methods=["POST"])
def link_document(job_id):
    job = db.get_or_404(Job, job_id)
    doc_id = request.form.get("document_id", type=int)
    if doc_id and db.session.get(Document, doc_id) and not JobDocument.query.filter_by(job_id=job.id, document_id=doc_id).first():
        db.session.add(JobDocument(job_id=job.id, document_id=doc_id))
        db.session.commit()
    return redirect(url_for("board.job_detail", job_id=job.id) + "#dokumente")


@bp.route("/job/<int:job_id>/documents/<int:doc_id>/unlink", methods=["POST"])
def unlink_document(job_id, doc_id):
    JobDocument.query.filter_by(job_id=job_id, document_id=doc_id).delete()
    db.session.commit()
    return redirect(url_for("board.job_detail", job_id=job_id) + "#dokumente")


# ---------------------------------------------------- Meine Unterlagen ----

ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "odt", "txt", "rtf", "pages", "png", "jpg", "jpeg"}
DOC_TYPES = [
    ("lebenslauf", "Lebenslauf"),
    ("anschreiben_vorlage", "Anschreiben-Vorlage"),
    ("zeugnis", "Zeugnis"),
    ("zertifikat", "Zertifikat"),
    ("showreel", "Showreel / Arbeitsproben"),
    ("sonstiges", "Sonstiges"),
]


def _allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@bp.route("/unterlagen")
def documents():
    docs = Document.query.order_by(Document.doc_type, Document.title).all()
    templates = CoverLetterTemplate.query.order_by(CoverLetterTemplate.name).all()
    return render_template("documents.html", docs=docs, doc_types=DOC_TYPES, doc_type_labels=dict(DOC_TYPES),
                           templates=templates, placeholders=PLACEHOLDERS)


@bp.route("/vorlagen", methods=["POST"])
@bp.route("/vorlagen/<int:template_id>", methods=["POST"])
def save_template(template_id=None):
    template = db.get_or_404(CoverLetterTemplate, template_id) if template_id else CoverLetterTemplate()
    name = request.form.get("name", "").strip()
    if not name:
        flash("Bitte der Vorlage einen Namen geben.", "error")
        return redirect(url_for("board.documents") + "#vorlagen")
    template.name = name[:120]
    template.body = request.form.get("body", "")
    db.session.add(template)
    db.session.commit()
    flash(f"Vorlage „{template.name}“ gespeichert.", "success")
    return redirect(url_for("board.documents") + "#vorlagen")


@bp.route("/vorlagen/<int:template_id>/delete", methods=["POST"])
def delete_template(template_id):
    db.session.delete(db.get_or_404(CoverLetterTemplate, template_id))
    db.session.commit()
    flash("Vorlage gelöscht.", "info")
    return redirect(url_for("board.documents") + "#vorlagen")


@bp.route("/unterlagen/upload", methods=["POST"])
def upload_document():
    file = request.files.get("file")
    doc_type = request.form.get("doc_type", "sonstiges")
    if doc_type not in dict(DOC_TYPES):
        doc_type = "sonstiges"
    if not file or not file.filename:
        flash("Bitte eine Datei auswählen.", "error")
        return redirect(url_for("board.documents"))
    if not _allowed_file(file.filename):
        flash("Dieser Dateityp wird nicht unterstützt (erlaubt: PDF, Word, Pages, Text, Bilder).", "error")
        return redirect(url_for("board.documents"))

    original_name = os.path.basename(file.filename)
    extension = original_name.rsplit(".", 1)[1].lower()
    safe_name = secure_filename(original_name) or f"dokument.{extension}"
    stored_name = f"{uuid.uuid4().hex}_{safe_name}"
    file.save(os.path.join(current_app.config["UPLOAD_DIR"], stored_name))

    title = request.form.get("title", "").strip() or original_name
    db.session.add(Document(doc_type=doc_type, title=title, filename=original_name, stored_path=stored_name))
    db.session.commit()
    flash("Dokument hochgeladen.", "success")
    return redirect(url_for("board.documents"))


@bp.route("/unterlagen/<int:doc_id>/delete", methods=["POST"])
def delete_document(doc_id):
    doc = db.get_or_404(Document, doc_id)
    JobDocument.query.filter_by(document_id=doc.id).delete()
    try:
        os.remove(os.path.join(current_app.config["UPLOAD_DIR"], doc.stored_path))
    except OSError:
        pass
    db.session.delete(doc)
    db.session.commit()
    flash("Dokument gelöscht.", "info")
    return redirect(url_for("board.documents"))


@bp.route("/unterlagen/<int:doc_id>/download")
def download_document(doc_id):
    doc = db.get_or_404(Document, doc_id)
    as_attachment = request.args.get("download") == "1"
    return send_from_directory(current_app.config["UPLOAD_DIR"], doc.stored_path,
                               download_name=doc.filename, as_attachment=as_attachment)


# ------------------------------------------------------ Job hinzufuegen ----


@bp.route("/job/neu", methods=["GET", "POST"])
def add_job():
    if request.method == "GET":
        return render_template("add_job.html")

    if request.form.get("mode") == "link":
        url = request.form.get("url", "").strip()
        existing = Job.query.filter_by(external_id=make_external_id(url)).first() if url else None
        if existing:
            flash("Dieser Job ist schon im Board.", "info")
            return redirect(url_for("board.job_detail", job_id=existing.id))
        try:
            listing, details = fetch_from_url(url, runtime_config())
        except ScraperError as exc:
            flash(f"{exc} – du kannst den Job unten auch von Hand anlegen.", "error")
            return redirect(url_for("board.add_job"))
        merge_details_into_listing(listing, details)
    else:
        title = request.form.get("title", "").strip()
        if not title:
            flash("Bitte mindestens einen Titel angeben.", "error")
            return redirect(url_for("board.add_job"))
        url = _clean_web_url(request.form.get("url", "")) or f"manuell://{uuid.uuid4().hex}"
        listing = JobListing(
            title=title, url=url, source="manuell",
            company=request.form.get("company", "").strip(),
            location=request.form.get("location", "").strip(),
            salary=request.form.get("salary", "").strip(),
            description=request.form.get("description", "").strip(),
        )
        details = empty_result()

    existing = Job.query.filter_by(external_id=make_external_id(listing.url)).first()
    if existing:
        flash("Dieser Job ist schon im Board.", "info")
        return redirect(url_for("board.job_detail", job_id=existing.id))

    score, label, reason = score_job(listing.title, listing.description, listing.location)
    job = job_from_listing(listing, details, score, label, reason)
    db.session.add(job)
    db.session.commit()
    flash("Job hinzugefügt.", "success")
    return redirect(url_for("board.job_detail", job_id=job.id))


# ------------------------------------------------------------- Firmen ----


@bp.route("/firmen")
def companies():
    sources = CompanySource.query.order_by(CompanySource.name).all()
    return render_template("companies.html", sources=sources, suggestions=open_suggestions(sources))


@bp.route("/firmen/vorschlaege", methods=["POST"])
def add_suggestions():
    wanted = request.form.get("name")  # leer = alle
    existing = CompanySource.query.all()
    added = []
    for suggestion in open_suggestions(existing):
        if wanted and suggestion["name"] != wanted:
            continue
        db.session.add(CompanySource(name=suggestion["name"], career_url=suggestion["url"], active=True))
        added.append(suggestion["name"])
    db.session.commit()
    if added:
        flash(f"Hinzugefügt: {', '.join(added)}. Wird ab dem nächsten Suchlauf durchsucht.", "success")
    return redirect(url_for("board.companies"))


@bp.route("/firmen/hinzufuegen", methods=["POST"])
def add_company():
    name = request.form.get("name", "").strip()
    url = _clean_web_url(request.form.get("career_url", ""))
    if not name or not url:
        flash("Bitte Firmenname und einen gültigen Link zur Karriereseite angeben.", "error")
        return redirect(url_for("board.companies"))
    if CompanySource.query.filter_by(name=name).first():
        flash("Eine Firma mit diesem Namen gibt es schon.", "error")
        return redirect(url_for("board.companies"))
    db.session.add(CompanySource(name=name, career_url=url, active=True))
    db.session.commit()
    flash(f"{name} hinzugefügt – wird ab dem nächsten Suchlauf mit durchsucht.", "success")
    return redirect(url_for("board.companies"))


@bp.route("/firmen/<int:source_id>/toggle", methods=["POST"])
def toggle_company(source_id):
    source = db.get_or_404(CompanySource, source_id)
    source.active = not source.active
    db.session.commit()
    return redirect(url_for("board.companies"))


@bp.route("/firmen/<int:source_id>/delete", methods=["POST"])
def delete_company(source_id):
    source = db.get_or_404(CompanySource, source_id)
    ScraperRun.query.filter_by(source=source.source_key).delete()
    db.session.delete(source)
    db.session.commit()
    flash(f"{source.name} entfernt.", "info")
    return redirect(url_for("board.companies"))


# ------------------------------------------------------- Einstellungen ----

API_KEY_FIELDS = [
    ("adzuna_app_id", "Adzuna App ID", "https://developer.adzuna.com"),
    ("adzuna_app_key", "Adzuna App Key", "https://developer.adzuna.com"),
    ("jooble_key", "Jooble API-Schlüssel", "https://jooble.org/api/about"),
    ("serpapi_key", "SerpApi-Schlüssel (Google Jobs)", "https://serpapi.com"),
]


@bp.route("/einstellungen")
def settings():
    config = runtime_config()
    settings_by_name = {s.name: s for s in SourceSetting.query.all()}
    sources = []
    for name, module in REGISTRY.items():
        setting = settings_by_name.get(name)
        sources.append({
            "name": name,
            "label": SOURCE_LABELS.get(name, name),
            "hint": SOURCE_HINTS.get(name, ""),
            "enabled": bool(setting and setting.enabled),
            "missing": missing_settings(module, config),
        })
    keys = AppSetting.as_dict()
    return render_template(
        "settings.html",
        profiles=SearchProfile.query.order_by(SearchProfile.location, SearchProfile.keywords).all(),
        sources=sources,
        key_fields=[(k, label, link, bool(keys.get(k))) for k, label, link in API_KEY_FIELDS],
    )


@bp.route("/einstellungen/profil", methods=["POST"])
def add_profile():
    keywords = request.form.get("keywords", "").strip()
    location = request.form.get("location", "").strip()
    radius = request.form.get("radius_km", type=int) or 25
    if not keywords:
        flash("Bitte einen Suchbegriff angeben.", "error")
    else:
        db.session.add(SearchProfile(keywords=keywords, location=location, radius_km=max(0, min(radius, 200))))
        db.session.commit()
        flash(f"Suchprofil „{keywords}“ angelegt.", "success")
    return redirect(url_for("board.settings") + "#profile")


@bp.route("/einstellungen/profil/<int:profile_id>/toggle", methods=["POST"])
def toggle_profile(profile_id):
    profile = db.get_or_404(SearchProfile, profile_id)
    profile.active = not profile.active
    db.session.commit()
    return redirect(url_for("board.settings") + "#profile")


@bp.route("/einstellungen/profil/<int:profile_id>/delete", methods=["POST"])
def delete_profile(profile_id):
    db.session.delete(db.get_or_404(SearchProfile, profile_id))
    db.session.commit()
    return redirect(url_for("board.settings") + "#profile")


@bp.route("/einstellungen/quelle/<name>/toggle", methods=["POST"])
def toggle_source(name):
    if name not in REGISTRY:
        return redirect(url_for("board.settings"))
    setting = db.session.get(SourceSetting, name) or SourceSetting(name=name, enabled=False)
    setting.enabled = not setting.enabled
    db.session.add(setting)
    db.session.commit()
    return redirect(url_for("board.settings") + "#quellen")


@bp.route("/einstellungen/schluessel", methods=["POST"])
def save_keys():
    for key, _, _ in API_KEY_FIELDS:
        value = request.form.get(key, "").strip()
        if request.form.get(f"clear_{key}"):
            value = ""
        elif not value:
            continue  # leeres Feld = bestehenden Schluessel behalten
        setting = db.session.get(AppSetting, key) or AppSetting(key=key)
        setting.value = value
        db.session.add(setting)
    db.session.commit()
    flash("Schlüssel gespeichert.", "success")
    return redirect(url_for("board.settings") + "#schluessel")


# ----------------------------------------------------------- Suchlauf ----


@bp.route("/fetch-now", methods=["POST"])
def fetch_now():
    if start_async(current_app._get_current_object()):
        flash("Suche gestartet – neue Jobs erscheinen automatisch, du kannst normal weiterarbeiten.", "info")
    else:
        flash("Es läuft bereits eine Suche.", "info")
    return redirect(_safe_next())


@bp.route("/fetch-status")
def fetch_status():
    return jsonify(snapshot())


# ------------------------------------------------------------- Status ----


def _app_version():
    try:
        out = subprocess.run(["git", "log", "-1", "--format=%h %cd", "--date=format:%d.%m.%Y %H:%M"],
                             cwd=BASE_DIR, capture_output=True, text=True, timeout=3)
        return out.stdout.strip() or "unbekannt"
    except Exception:
        return "unbekannt"


@bp.route("/status")
def status():
    latest = latest_run_per_source()
    rows = [{"source": s, "label": source_label(s), "run": r, "kind": run_kind(r)} for s, r in latest.items()]
    return render_template("status.html", rows=rows, version=_app_version())


@bp.route("/status/text")
def status_text():
    """Klartext-Diagnose zum Kopieren an Claude."""
    config = runtime_config()
    enabled = sorted(s.name for s in SourceSetting.query.filter_by(enabled=True).all())
    lines = [
        "Bewerbungs-Board – Diagnose",
        "=" * 30,
        f"Version: {_app_version()}",
        f"Aktive Quellen: {', '.join(enabled) or 'keine'}",
        f"Fehlende Schlüssel: {', '.join(n for n in enabled if n in REGISTRY and missing_settings(REGISTRY[n], config)) or 'keine'}",
        f"Aktive Suchprofile: {SearchProfile.query.filter_by(active=True).count()}",
        f"Aktive Firmen: {CompanySource.query.filter_by(active=True).count()}",
        f"Jobs gesamt: {Job.query.count()}",
        "",
    ]
    latest = latest_run_per_source()
    if not latest:
        lines.append("Noch kein Suchlauf protokolliert.")
    for source, run in latest.items():
        lines.append(f"[{run_kind(run).upper()}] {source} – {run.ran_at:%Y-%m-%d %H:%M} UTC – neu: {run.new_jobs}")
        lines.append(f"    {run.message}")
    return "\n".join(lines) + "\n", 200, {"Content-Type": "text/plain; charset=utf-8"}
