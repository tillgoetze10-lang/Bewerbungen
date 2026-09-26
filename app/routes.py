import os
import uuid

from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from werkzeug.utils import secure_filename

from .config import load_config
from .extraction import EMPTY_RESULT, fetch_and_extract_details
from .fetch_jobs import run_fetch_cycle
from .matching import score_job
from .models import (
    STATUS_ARCHIVIERT,
    STATUS_FLOW,
    STATUS_KEYS,
    CompanySource,
    Document,
    Job,
    JobDocument,
    db,
    make_external_id,
)
from .scrapers.base import ScraperError
from .scrapers.quick_add import fetch_from_url
from .status import latest_run_per_source

bp = Blueprint("board", __name__)


@bp.route("/")
def board():
    columns = []
    for key, label in STATUS_FLOW:
        jobs = (
            Job.query.filter_by(status=key)
            .order_by(Job.match_score.desc(), Job.fetched_at.desc())
            .all()
        )
        columns.append({"key": key, "label": label, "jobs": jobs})
    archived_count = Job.query.filter_by(status=STATUS_ARCHIVIERT).count()
    return render_template("board.html", columns=columns, archived_count=archived_count)


@bp.route("/archiv")
def archive():
    jobs = Job.query.filter_by(status=STATUS_ARCHIVIERT).order_by(Job.updated_at.desc()).all()
    return render_template("archive.html", jobs=jobs)


@bp.route("/job/<int:job_id>/status", methods=["POST"])
def update_status(job_id):
    job = Job.query.get_or_404(job_id)
    data = request.get_json(silent=True) or request.form
    new_status = data.get("status")
    ok = new_status in STATUS_KEYS + [STATUS_ARCHIVIERT]
    if ok:
        job.status = new_status
        db.session.commit()

    if request.is_json:
        return jsonify({"ok": ok, "status": job.status})

    next_url = request.form.get("next") or url_for("board.board")
    return redirect(next_url)


@bp.route("/job/<int:job_id>/delete", methods=["POST"])
def delete_job(job_id):
    """'Loeschen' = Archivieren (nicht interessant), Daten bleiben erhalten.
    Endgueltiges Entfernen geht ueber /job/<id>/purge im Archiv."""
    job = Job.query.get_or_404(job_id)
    job.status = STATUS_ARCHIVIERT
    db.session.commit()
    return redirect(request.referrer or url_for("board.board"))


@bp.route("/job/<int:job_id>/purge", methods=["POST"])
def purge_job(job_id):
    job = Job.query.get_or_404(job_id)
    JobDocument.query.filter_by(job_id=job.id).delete()
    db.session.delete(job)
    db.session.commit()
    return redirect(url_for("board.archive"))


@bp.route("/job/<int:job_id>")
def job_detail(job_id):
    job = Job.query.get_or_404(job_id)
    linked_doc_ids = {jd.document_id for jd in job.documents}
    library_docs = Document.query.order_by(Document.doc_type, Document.title).all()
    linked_docs = [d for d in library_docs if d.id in linked_doc_ids]
    return render_template(
        "job_detail.html",
        job=job,
        status_flow=STATUS_FLOW,
        archiv_status=STATUS_ARCHIVIERT,
        library_docs=library_docs,
        linked_docs=linked_docs,
        linked_doc_ids=linked_doc_ids,
    )


@bp.route("/job/<int:job_id>/save", methods=["POST"])
def save_job(job_id):
    job = Job.query.get_or_404(job_id)
    job.cover_letter = request.form.get("cover_letter", "")
    job.notes = request.form.get("notes", "")
    job.contact_name = request.form.get("contact_name", "")
    job.contact_email = request.form.get("contact_email", "")
    job.contact_phone = request.form.get("contact_phone", "")
    job.company_website = request.form.get("company_website", "")
    job.requirements = request.form.get("requirements", "")
    job.application_documents = request.form.get("application_documents", "")
    db.session.commit()
    flash("Gespeichert.", "success")
    return redirect(url_for("board.job_detail", job_id=job.id))


@bp.route("/job/<int:job_id>/reextract", methods=["POST"])
def reextract_job(job_id):
    """Ruft die Original-Anzeige erneut ab und aktualisiert Ansprechpartner/
    Website/Voraussetzungen/Bewerbungsunterlagen - falls sich die Anzeige
    geaendert hat oder die erste Extraktion nichts fand."""
    job = Job.query.get_or_404(job_id)
    details = fetch_and_extract_details(job.url, load_config())
    if not details:
        flash(
            "Anzeige konnte nicht erneut abgerufen werden (Link tot, Bot-Schutz "
            "oder robots.txt untersagt es). Bitte Felder manuell pruefen.",
            "error",
        )
        return redirect(url_for("board.job_detail", job_id=job.id))

    job.contact_name = details["contact_name"] or job.contact_name
    job.contact_email = details["contact_email"] or job.contact_email
    job.contact_phone = details["contact_phone"] or job.contact_phone
    job.company_website = details["company_website"] or job.company_website
    job.requirements = details["requirements"] or job.requirements
    job.application_documents = details["application_documents"] or job.application_documents
    job.extraction_confidence = details["confidence"]
    job.extraction_missing = ",".join(details["missing_fields"])
    db.session.commit()
    flash(f"Neu extrahiert: {job.extraction_confidence_text()}.", "info")
    return redirect(url_for("board.job_detail", job_id=job.id))


@bp.route("/job/<int:job_id>/documents/link", methods=["POST"])
def link_document(job_id):
    job = Job.query.get_or_404(job_id)
    doc_id = request.form.get("document_id", type=int)
    if doc_id and not JobDocument.query.filter_by(job_id=job.id, document_id=doc_id).first():
        db.session.add(JobDocument(job_id=job.id, document_id=doc_id))
        db.session.commit()
    return redirect(url_for("board.job_detail", job_id=job.id))


@bp.route("/job/<int:job_id>/documents/<int:doc_id>/unlink", methods=["POST"])
def unlink_document(job_id, doc_id):
    JobDocument.query.filter_by(job_id=job_id, document_id=doc_id).delete()
    db.session.commit()
    return redirect(url_for("board.job_detail", job_id=job_id))


# ---- Zentrale Dokumentenbibliothek ("Meine Unterlagen") ----

ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "odt", "txt", "png", "jpg", "jpeg"}


def _allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@bp.route("/unterlagen")
def documents():
    docs = Document.query.order_by(Document.doc_type, Document.title).all()
    return render_template("documents.html", docs=docs)


@bp.route("/unterlagen/upload", methods=["POST"])
def upload_document():
    file = request.files.get("file")
    doc_type = request.form.get("doc_type", "sonstiges")
    title = request.form.get("title") or (file.filename if file else "")

    if not file or file.filename == "":
        flash("Bitte eine Datei auswaehlen.", "error")
        return redirect(url_for("board.documents"))
    if not _allowed_file(file.filename):
        flash("Dateityp nicht erlaubt.", "error")
        return redirect(url_for("board.documents"))

    safe_name = secure_filename(file.filename)
    stored_name = f"{uuid.uuid4().hex}_{safe_name}"
    file.save(os.path.join(current_app.config["UPLOAD_DIR"], stored_name))

    doc = Document(doc_type=doc_type, title=title, filename=safe_name, stored_path=stored_name)
    db.session.add(doc)
    db.session.commit()
    flash("Dokument hochgeladen.", "success")
    return redirect(url_for("board.documents"))


@bp.route("/unterlagen/<int:doc_id>/delete", methods=["POST"])
def delete_document(doc_id):
    doc = Document.query.get_or_404(doc_id)
    JobDocument.query.filter_by(document_id=doc.id).delete()
    try:
        os.remove(os.path.join(current_app.config["UPLOAD_DIR"], doc.stored_path))
    except OSError:
        pass
    db.session.delete(doc)
    db.session.commit()
    return redirect(url_for("board.documents"))


@bp.route("/unterlagen/<int:doc_id>/download")
def download_document(doc_id):
    doc = Document.query.get_or_404(doc_id)
    return send_from_directory(current_app.config["UPLOAD_DIR"], doc.stored_path, download_name=doc.filename)


# ---- Manuelles Hinzufuegen ----


@bp.route("/job/neu", methods=["GET", "POST"])
def add_job():
    if request.method == "GET":
        return render_template("add_job.html")

    mode = request.form.get("mode")

    if mode == "link":
        url = request.form.get("url", "").strip()
        if not url:
            flash("Bitte einen Link angeben.", "error")
            return redirect(url_for("board.add_job"))
        try:
            listing, details = fetch_from_url(url, load_config())
        except ScraperError as exc:
            flash(str(exc), "error")
            return redirect(url_for("board.add_job"))

        ext_id = make_external_id(listing.url)
        existing = Job.query.filter_by(external_id=ext_id).first()
        if existing:
            flash("Dieser Job ist schon im Board.", "info")
            return redirect(url_for("board.job_detail", job_id=existing.id))

        score, label, reason = score_job(listing.title, listing.description, listing.location)
        job = Job(
            external_id=ext_id,
            title=listing.title,
            company=listing.company,
            location=listing.location,
            url=listing.url,
            source=listing.source,
            salary=listing.salary,
            description=listing.description,
            posted_at=listing.posted_at,
            status="neu",
            match_score=score,
            match_label=label,
            match_reason=reason,
            contact_name=details["contact_name"],
            contact_email=details["contact_email"],
            contact_phone=details["contact_phone"],
            company_website=details["company_website"],
            requirements=details["requirements"],
            application_documents=details["application_documents"],
            extraction_confidence=details["confidence"],
            extraction_missing=",".join(details["missing_fields"]),
        )
        db.session.add(job)
        db.session.commit()
        flash("Job hinzugefuegt.", "success")
        return redirect(url_for("board.job_detail", job_id=job.id))

    # mode == "manual": komplett von Hand ausgefuelltes Formular
    title = request.form.get("title", "").strip()
    url = request.form.get("url", "").strip() or f"manuell://{uuid.uuid4().hex}"
    if not title:
        flash("Bitte mindestens einen Titel angeben.", "error")
        return redirect(url_for("board.add_job"))

    description = request.form.get("description", "")
    location = request.form.get("location", "")
    score, label, reason = score_job(title, description, location)

    ext_id = make_external_id(url)
    job = Job(
        external_id=ext_id,
        title=title,
        company=request.form.get("company", ""),
        location=location,
        url=url,
        source="manuell",
        salary=request.form.get("salary", ""),
        description=description,
        status="neu",
        match_score=score,
        match_label=label,
        match_reason=reason,
    )
    db.session.add(job)
    db.session.commit()
    flash("Job hinzugefuegt.", "success")
    return redirect(url_for("board.job_detail", job_id=job.id))


# ---- Firmen-Karriereseiten ----


@bp.route("/firmen")
def companies():
    sources = CompanySource.query.order_by(CompanySource.name).all()
    return render_template("companies.html", sources=sources)


@bp.route("/firmen/hinzufuegen", methods=["POST"])
def add_company():
    name = request.form.get("name", "").strip()
    url = request.form.get("career_url", "").strip()
    if not name or not url:
        flash("Bitte Firmenname und Link zur Karriereseite angeben.", "error")
        return redirect(url_for("board.companies"))
    db.session.add(CompanySource(name=name, career_url=url, active=True))
    db.session.commit()
    flash(f"{name} hinzugefuegt. Wird beim naechsten Fetch-Lauf mit durchsucht.", "success")
    return redirect(url_for("board.companies"))


@bp.route("/firmen/<int:source_id>/toggle", methods=["POST"])
def toggle_company(source_id):
    source = CompanySource.query.get_or_404(source_id)
    source.active = not source.active
    db.session.commit()
    return redirect(url_for("board.companies"))


@bp.route("/firmen/<int:source_id>/delete", methods=["POST"])
def delete_company(source_id):
    source = CompanySource.query.get_or_404(source_id)
    db.session.delete(source)
    db.session.commit()
    return redirect(url_for("board.companies"))


# ---- Manuellen Scraper-Lauf anstossen ----


@bp.route("/fetch-now", methods=["POST"])
def fetch_now():
    result = run_fetch_cycle(current_app._get_current_object())
    if result["new_jobs"]:
        flash(f"{result['new_jobs']} neue Job(s) gefunden.", "success")
    else:
        flash("Keine neuen Jobs gefunden.", "info")
    for err in result["errors"]:
        flash(err, "error")
    return redirect(url_for("board.board"))


# ---- Status: dauerhaftes Protokoll statt fluechtiger Flash-Meldungen ----


@bp.route("/status")
def status():
    latest = latest_run_per_source()
    broken = [s for s, r in latest.items() if not r.ok]
    return render_template("status.html", latest=latest, broken=broken)


@bp.route("/status/text")
def status_text():
    """Reiner Text-Dump zum Kopieren - schick das einfach 1:1 weiter, wenn
    eine Quelle nicht funktioniert, dann muss niemand die Meldungen selbst
    verstehen."""
    lines = ["Bewerbungs-Board - Quellen-Status", "=" * 34, ""]
    latest = latest_run_per_source()
    if not latest:
        lines.append("Noch kein Fetch-Lauf protokolliert. Einmal 'Jetzt nach neuen Jobs suchen' klicken.")
    for source, run in latest.items():
        state = "OK" if run.ok else "FEHLER"
        lines.append(f"[{state}] {source} - zuletzt {run.ran_at.strftime('%Y-%m-%d %H:%M UTC')}")
        lines.append(f"    {run.message}")
        lines.append("")
    return "\n".join(lines), 200, {"Content-Type": "text/plain; charset=utf-8"}
