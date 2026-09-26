"""Ein kompletter Suchlauf: alle aktiven Quellen x alle aktiven Suchprofile
+ alle hinterlegten Firmen-Karriereseiten. Neue, passende Jobs landen im
Status "neu", jeder Quellen-Versuch wird als ScraperRun protokolliert.

Aufruf im Hintergrund: app/fetch_runner.py (Button + Scheduler)
Aufruf von Hand:       python -m app.fetch_jobs
"""

import logging
import sys
from datetime import date, timedelta

from sqlalchemy.exc import IntegrityError

from .config import load_config
from .extraction import empty_result, extract_details
from .matching import score_job, score_title
from .models import (
    AppSetting, CompanySource, Job, ScraperRun, SearchProfile, SourceSetting, db, make_external_id, utcnow,
)
from .scrapers import REGISTRY, source_label
from .scrapers.base import ScraperError
from .scrapers.company_generic import search_company
from .scrapers.http_utils import get

logger = logging.getLogger(__name__)

RUNS_KEPT_PER_SOURCE = 20
# Nach so vielen "blockiert"-Antworten in Folge wird eine Quelle fuer den
# Rest des Laufs uebersprungen - sonst wartet man z.B. 12x auf StepStone-Timeouts.
BLOCKED_STREAK_LIMIT = 1
# Kostenpflichtige/limitierte APIs nicht stuendlich abfragen.
MIN_HOURS_BETWEEN_RUNS = {"google_jobs": 24}


def runtime_config():
    """config.yaml + im UI gespeicherte Schluessel (UI hat Vorrang)."""
    config = load_config()
    config.update(AppSetting.as_dict())
    return config


def enabled_source_names():
    return {s.name for s in SourceSetting.query.filter_by(enabled=True).all()}


def missing_settings(module, config):
    return [key for key in getattr(module, "REQUIRED_SETTINGS", []) if not config.get(key)]


def _assume_film_context(source: str) -> bool:
    return source == "crewunited" or source.startswith("firma:")


def load_details(listing, config):
    """Detailseite laden (quellenspezifisch oder per HTTP) und auslesen."""
    module = REGISTRY.get(listing.source)
    try:
        if module is not None and hasattr(module, "detail_html"):
            page = module.detail_html(listing, config)
        else:
            page = get(listing.url, config)
    except ScraperError as exc:
        logger.info("Details fuer %s nicht abrufbar: %s", listing.url, exc)
        return None
    if not page:
        return None
    try:
        return extract_details(page, page_url=listing.url, company_page=listing.source.startswith("firma:"))
    except Exception:
        logger.exception("Detail-Auslesen fehlgeschlagen fuer %s", listing.url)
        return None


def merge_details_into_listing(listing, details):
    """Fehlende Grunddaten (Ort, Firma, Beschreibung ...) aus der Detailseite ergaenzen."""
    for key, value in (details.get("listing") or {}).items():
        if value and not getattr(listing, key, ""):
            setattr(listing, key, value)
    if len(listing.description or "") < 200 and len(details.get("page_text") or "") > len(listing.description or ""):
        listing.description = details["page_text"]


DETAIL_FIELDS = ("tasks", "requirements", "application_documents", "contact_name", "contact_salutation",
                 "contact_email", "contact_phone", "company_website")


def apply_details(job, details):
    for field in DETAIL_FIELDS:
        setattr(job, field, details.get(field, "") or "")
    if details.get("deadline"):
        try:
            job.deadline = date.fromisoformat(details["deadline"])
        except ValueError:
            pass
    job.extraction_confidence = details.get("confidence", "unsicher")
    job.extraction_missing = ",".join(details.get("missing_fields", []))


def job_from_listing(listing, details, score, label, reason):
    job = Job(
        external_id=make_external_id(listing.url),
        title=listing.title[:300],
        company=(listing.company or "")[:200],
        location=(listing.location or "")[:200],
        url=listing.url,
        source=listing.source,
        source_ref=listing.ref or "",
        salary=(listing.salary or "")[:200],
        description=listing.description or "",
        posted_at=(listing.posted_at or "")[:50],
        status="neu",
        match_score=score,
        match_label=label,
        match_reason=reason,
    )
    apply_details(job, details or empty_result())
    return job


def store_listing(listing, config, seen_ids, new_top=None) -> bool:
    """Legt einen Job an, falls neu und fachlich passend. True = neu angelegt.
    Titel neuer Top-Treffer landen in new_top (fuer die Mac-Mitteilung)."""
    if not listing.is_valid():
        return False
    ext_id = make_external_id(listing.url)
    if ext_id in seen_ids or Job.query.filter_by(external_id=ext_id).first():
        return False
    seen_ids.add(ext_id)

    assume = _assume_film_context(listing.source)
    first_look = score_title(listing.title, listing.description, assume)
    if first_look.score == 0 and not first_look.candidate:
        return False  # offensichtlich kein Video/Film-Job -> nicht mal Details laden

    details = load_details(listing, config) if config.get("fetch_job_details", True) else None
    if details:
        merge_details_into_listing(listing, details)

    score, label, reason = score_job(listing.title, listing.description, listing.location, assume)
    if score == 0:
        return False

    db.session.add(job_from_listing(listing, details, score, label, reason))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return False
    if new_top is not None and label == "top":
        new_top.append(listing.title)
    return True


def _record_run(source: str, kind: str, message: str, new_jobs: int):
    run = ScraperRun(source=source, ok=(kind == "ok"), kind=kind, message=message[:2000], new_jobs=new_jobs)
    db.session.add(run)
    db.session.flush()
    run_id = run.id
    old_ids = [
        r.id for r in ScraperRun.query.filter_by(source=source)
        .order_by(ScraperRun.ran_at.desc()).offset(RUNS_KEPT_PER_SOURCE).all()
    ]
    if old_ids:
        ScraperRun.query.filter(ScraperRun.id.in_(old_ids)).delete(synchronize_session=False)
    db.session.commit()
    return run_id


def _resolve_network_runs(run_ids, any_success: bool):
    """Verbindungsfehler: Klappt keine einzige Quelle, ist schlicht das Internet
    weg ("offline", kein Alarm). Klappen andere, ist die eine Quelle wirklich
    kaputt/umgezogen ("error", Claude soll draufschauen)."""
    runs = ScraperRun.query.filter(ScraperRun.id.in_(run_ids), ScraperRun.kind == "network").all()
    for run in runs:
        run.kind = "error" if any_success else "offline"
    db.session.commit()
    return not any_success and bool(runs)


def _summarize(attempts: int, errors, new_jobs: int, skipped: int):
    """Mehrere Versuche einer Quelle zu einem Status zusammenfassen."""
    unique = list(dict.fromkeys(str(e) for e in errors))
    text = "; ".join(unique[:3]) + (f" (+{len(unique) - 3} weitere)" if len(unique) > 3 else "")
    if skipped:
        text += f" – restliche {skipped} Suche(n) übersprungen."
    succeeded = attempts - len(errors)
    if succeeded > 0:
        msg = f"{new_jobs} neue Job(s)."
        if errors:
            msg += f" {len(errors)} von {attempts} Suchen fehlgeschlagen: {text}"
        return "ok", msg
    kinds = {getattr(e, "kind", "error") for e in errors}
    for kind in ("error", "network", "config", "blocked"):
        if kind in kinds:
            break
    return kind, text or "Keine Suche erfolgreich."


def _run_source(name, module, profiles, config, seen_ids, progress, new_top):
    runs = profiles if getattr(module, "PER_PROFILE", True) else profiles[:1]
    new_jobs, errors, blocked_streak, attempts = 0, [], 0, 0
    for index, profile in enumerate(runs):
        if blocked_streak >= BLOCKED_STREAK_LIMIT:
            return new_jobs, errors, attempts, len(runs) - index
        attempts += 1
        progress(f"{source_label(name)}: {profile.get('keywords') or 'alle'}"
                 + (f" in {profile['location']}" if profile.get("location") else ""))
        try:
            listings = module.search(profile, config)
            blocked_streak = 0
        except ScraperError as exc:
            errors.append(exc)
            blocked_streak = blocked_streak + 1 if exc.kind in ("blocked", "config", "network") else 0
            continue
        except Exception as exc:
            logger.exception("[%s] unerwarteter Fehler", name)
            errors.append(ScraperError(f"Unerwarteter Fehler: {type(exc).__name__}: {exc}"))
            continue
        for listing in listings:
            try:
                if store_listing(listing, config, seen_ids, new_top):
                    new_jobs += 1
            except Exception:
                logger.exception("[%s] Job konnte nicht gespeichert werden: %s", name, listing.url)
                db.session.rollback()
    return new_jobs, errors, attempts, 0


def _recently_ran(source: str, hours: int) -> bool:
    last = ScraperRun.query.filter_by(source=source, ok=True).order_by(ScraperRun.ran_at.desc()).first()
    if not last or not last.ran_at:
        return False
    ran_at = last.ran_at if last.ran_at.tzinfo else last.ran_at.replace(tzinfo=utcnow().tzinfo)
    return utcnow() - ran_at < timedelta(hours=hours)


def run_fetch_cycle(app, progress=None):
    progress = progress or (lambda step: None)
    total_new, problems, run_ids, any_success, new_top = 0, [], [], False, []

    with app.app_context():
        config = runtime_config()
        profiles = [p.as_dict() for p in SearchProfile.query.filter_by(active=True).order_by(SearchProfile.id).all()]
        enabled = enabled_source_names()
        seen_ids = set()

        for name, module in REGISTRY.items():
            if name not in enabled or missing_settings(module, config):
                continue
            if name in MIN_HOURS_BETWEEN_RUNS and _recently_ran(name, MIN_HOURS_BETWEEN_RUNS[name]):
                continue
            if not profiles:
                _record_run(name, "config", "Keine aktiven Suchprofile – unter Einstellungen anlegen.", 0)
                continue
            new_jobs, errors, attempts, skipped = _run_source(name, module, profiles, config, seen_ids, progress, new_top)
            kind, message = _summarize(attempts, errors, new_jobs, skipped)
            run_ids.append(_record_run(name, kind, message, new_jobs))
            total_new += new_jobs
            any_success = any_success or kind == "ok"
            if kind != "ok":
                problems.append((name, kind, message))

        for company in CompanySource.query.filter_by(active=True).all():
            progress(f"Firma: {company.name}")
            try:
                listings = search_company(company.name, company.career_url, config)
            except ScraperError as exc:
                company.last_result = f"{'Blockiert' if exc.kind == 'blocked' else 'Fehler'}: {exc}"[:290]
                run_ids.append(_record_run(company.source_key, exc.kind, str(exc), 0))
                problems.append((company.source_key, exc.kind, str(exc)))
                continue
            except Exception as exc:
                logger.exception("[%s] unerwarteter Fehler", company.source_key)
                db.session.rollback()
                message = f"Unerwarteter Fehler: {type(exc).__name__}: {exc}"
                company.last_result = message[:290]
                _record_run(company.source_key, "error", message, 0)
                problems.append((company.source_key, "error", message))
                continue

            found = 0
            for listing in listings:
                try:
                    if store_listing(listing, config, seen_ids, new_top):
                        found += 1
                except Exception:
                    logger.exception("[%s] Job konnte nicht gespeichert werden", company.source_key)
                    db.session.rollback()
            company.last_result = f"{len(listings)} passende Stelle(n), davon {found} neu."
            _record_run(company.source_key, "ok", company.last_result, found)
            total_new += found
            any_success = True

        offline = _resolve_network_runs(run_ids, any_success)
        problems = [(s, ("offline" if offline else "error") if k == "network" else k, m) for s, k, m in problems]
        db.session.commit()

    logger.info("Suchlauf fertig: %s neue Jobs, %s Quelle(n) mit Problemen", total_new, len(problems))
    return {"new_jobs": total_new, "problems": problems, "offline": offline, "new_top": new_top}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from . import create_app

    result = run_fetch_cycle(create_app(), progress=lambda step: print(" ...", step))
    print(f"Neue Jobs: {result['new_jobs']}")
    for source, kind, message in result["problems"]:
        print(f"  [{kind}] {source}: {message}")
    sys.exit(0)
