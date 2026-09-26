"""Tests ohne Internet: Jobboersen werden mit festen Antworten simuliert.

Ausfuehren:  .venv/bin/python -m unittest discover -s tests -v
"""

import io
import json
import os
import sqlite3
import tempfile
import time
import unittest
from unittest import mock

import requests

import app.scrapers.http_utils as http_utils
from app import create_app
from app.extraction import extract_details
from app.matching import score_job
from app.models import AppSetting, CompanySource, Job, ScraperRun, SearchProfile, SourceSetting, db

http_utils._MIN_SECONDS_BETWEEN_REQUESTS_PER_HOST = 0


class FakeResponse:
    def __init__(self, status=200, text="", json_data=None, content_type="text/html; charset=utf-8"):
        self.status_code = status
        self._json = json_data
        self.text = text if json_data is None else json.dumps(json_data)
        self.content = self.text.encode("utf-8")
        self.headers = {"Content-Type": "application/json" if json_data is not None else content_type}
        self.encoding = "utf-8"
        self.apparent_encoding = "utf-8"

    def json(self):
        if self._json is None:
            raise ValueError("kein JSON")
        return self._json


ADZUNA_SEARCH = {
    "results": [
        {"id": 111, "title": "Mediengestalter/in <strong>Bild und Ton</strong>", "company": {"display_name": "Beispiel Studios GmbH"},
         "location": {"display_name": "Köln, Nordrhein-Westfalen"}, "redirect_url": "https://www.adzuna.de/details/111",
         "description": "Schnitt und Kamera für TV-Beiträge", "created": "2026-09-20T10:00:00Z"},
        {"id": 222, "title": "Kreditorenbuchhalter (m/w/d)", "company": {"display_name": "Zahlen AG"},
         "location": {"display_name": "Köln"}, "redirect_url": "https://www.adzuna.de/details/222", "description": "Buchhaltung"},
    ]
}
ADZUNA_DETAIL = """<html><body><h1>Mediengestalter/in Bild und Ton</h1>
<h3>Deine Aufgaben</h3><ul><li>Schnitt von TV-Beiträgen</li><li>Kamera bei Außendrehs</li></ul>
<h3>Dein Profil</h3><ul><li>Ausbildung als Mediengestalter</li><li>Premiere Pro</li></ul>
<p>Bitte sende Lebenslauf und Showreel an Frau Anna Schmidt, bewerbung@beispiel-studios.de</p></body></html>"""
CREW_LIST = """<html><body>
<a href="/de/jobs/">Alle Jobs</a>
<a href="/de/jobs/12345_setrunner-fuer-kinofilm/">Setrunner (m/w/d) für Kinofilm – Drehtage im Oktober</a>
<a href="/de/jobs/12346_catering/">Catering-Hilfe (m/w/d)</a>
</body></html>"""
CREW_DETAIL = """<html><body><h1>Setrunner (m/w/d)</h1><p>Ort: Hamburg. Drehtage im Oktober, Tagesgage.</p>
<h3>Deine Aufgaben</h3><ul><li>Unterstützung am Set</li></ul></body></html>"""
COMPANY_PAGE = """<html><body><nav><a href="/postproduktion">Postproduktion</a><a href="/kamera">Kamera</a></nav>
<h2>Offene Stellen</h2>
<a href="/karriere/video-editor">Video Editor (m/w/d)</a>
<a href="/karriere/buchhaltung">Buchhaltung (m/w/d)</a></body></html>"""
COMPANY_JOB = """<html><body><h1>Video Editor (m/w/d)</h1><p>Standort Köln-Ossendorf</p>
<h3>Das bringst du mit</h3><ul><li>Avid oder Premiere</li><li>Gefühl für Timing</li></ul>
<p>Ansprechpartner: Tom Becker, jobs@filmhaus-koeln.de</p></body></html>"""


def fake_get(url, headers=None, params=None, timeout=None, **kwargs):
    if url.endswith("/robots.txt"):
        return FakeResponse(404)
    if url.startswith("https://api.adzuna.com/"):
        assert params["app_id"] == "id1" and params["app_key"] == "key1"
        return FakeResponse(json_data=ADZUNA_SEARCH)
    if url == "https://www.adzuna.de/details/111":
        return FakeResponse(text=ADZUNA_DETAIL)
    if url.rstrip("/").endswith("crew-united.com/de/jobs"):
        return FakeResponse(text=CREW_LIST)
    if "crew-united.com/de/jobs/12345" in url:
        return FakeResponse(text=CREW_DETAIL)
    if url == "https://filmhaus-koeln.de/karriere":
        return FakeResponse(text=COMPANY_PAGE)
    if url == "https://filmhaus-koeln.de/karriere/video-editor":
        return FakeResponse(text=COMPANY_JOB)
    if "indeed.com" in url:
        return FakeResponse(403, text="Forbidden")
    if "stepstone.de" in url:
        raise requests.Timeout("read timed out")
    return FakeResponse(404)


class AppTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp.name, "test.db")
        self.app = create_app(database_uri=f"sqlite:///{self.db_path}")
        self.app.config["UPLOAD_DIR"] = self.tmp.name
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()
        http_utils._robots_cache.clear()
        for key, value in (("adzuna_app_id", "id1"), ("adzuna_app_key", "key1")):
            db.session.add(AppSetting(key=key, value=value))
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.engine.dispose()
        self.ctx.pop()
        self.tmp.cleanup()

    def run_fetch(self):
        from app.fetch_jobs import run_fetch_cycle

        with mock.patch.object(http_utils.requests, "get", side_effect=fake_get):
            return run_fetch_cycle(self.app)


class MatchingTests(unittest.TestCase):
    CASES = [
        ("Kreditorenbuchhalter (m/w/d)", "Buchhaltung", "Köln", "raus"),
        ("Runner (m/w/d) Restaurant", "Service im Restaurant, Kennenlernen per Video", "Köln", "raus"),
        ("Produktionsleitung Metallbau", "Fertigung, Schnittstelle zum Vertrieb, Dreher", "Köln", "raus"),
        ("Account Manager Software", "Vertrieb SaaS, Videocall", "Köln", "raus"),
        ("Mediengestalter Digital und Print", "Printprodukte, Flyer", "Köln", "raus"),
        ("Kameraassistent", "unbefristeter Vertrag", "München", "unpassend"),
        ("Video Editor (m/w/d)", "Schnitt von Werbeclips", "Köln", "top"),
        ("Mediengestalter/in Bild und Ton", "", "Köln, Nordrhein-Westfalen", "top"),
        ("Runner (m/w/d)", "Unterstützung am Set bei TV-Serie, Drehtage im Oktober", "Hamburg", "top"),
        ("Aufnahmeleitung (m/w/d)", "Kinofilm", "Frankfurt am Main", "top"),
        ("Video Producer", "Corporate Videos für Kunden", "Frankfurt am Main", "unpassend"),
        ("Editor (m/w/d)", "Videoschnitt in Premiere Pro und After Effects", "Hürth", "top"),
        ("Setrunner", "Drehtage im März, Tagesgage", "Berlin", "top"),
        ("Cutter", "Dokumentarfilm, Avid", "", "pruefen"),
        ("Video Editor", "Postproduktion", "Remote", "top"),
        ("Kameramann (m/w/d)", "Festanstellung", "Frankfurt (Oder)", "unpassend"),
    ]

    def test_cases(self):
        for title, desc, loc, expected in self.CASES:
            with self.subTest(title=title, location=loc):
                score, label, _ = score_job(title, desc, loc)
                self.assertEqual("raus" if score == 0 else label, expected)


class ExtractionTests(unittest.TestCase):
    def test_full_page(self):
        page = """<nav>Kontakt Impressum</nav><h3>Deine Aufgaben</h3><ul><li>Schnitt</li></ul>
        <h3>Dein Profil</h3><ul><li>Premiere Pro</li></ul><h3>Wir bieten</h3><ul><li>Obst</li></ul>
        <p>Schick uns Lebenslauf und Showreel.</p>
        <p>Ansprechpartnerin: Frau Julia Beispiel, julia.beispiel(at)filmfirma.de, Tel.: 0221 / 123 45 67</p>
        <footer>info@filmfirma.de</footer>"""
        d = extract_details(page, page_url="https://jobs.personio.de/x")
        self.assertEqual(d["tasks"], "• Schnitt")
        self.assertEqual(d["requirements"], "• Premiere Pro")
        self.assertIn("Showreel", d["application_documents"])
        self.assertEqual(d["contact_name"], "Julia Beispiel")
        self.assertEqual(d["contact_email"], "julia.beispiel@filmfirma.de")
        self.assertEqual(d["contact_phone"], "0221 / 123 45 67")
        self.assertEqual(d["company_website"], "https://filmfirma.de")

    def test_no_false_positives(self):
        d = extract_details("<p>Kontakt: bei Fragen wende dich an uns.</p><p>Wir suchen Freelancer.</p>"
                            "<p>Unternehmensprofil</p><footer>Kontakt Impressum Datenschutz</footer>")
        self.assertEqual(d["contact_name"], "")
        self.assertEqual(d["application_documents"], "")
        self.assertEqual(d["requirements"], "")
        self.assertEqual(d["confidence"], "unsicher")


class FetchCycleTests(AppTestCase):
    def test_full_cycle(self):
        SourceSetting.query.filter_by(name="indeed").first().enabled = True
        SourceSetting.query.filter_by(name="stepstone").first().enabled = True
        SearchProfile.query.delete()
        db.session.add(SearchProfile(keywords="Mediengestalter", location="Köln", radius_km=25))
        db.session.add(SearchProfile(keywords="Video Editor", location="Köln", radius_km=25))
        db.session.add(CompanySource(name="Filmhaus Köln", career_url="https://filmhaus-koeln.de/karriere"))
        db.session.commit()

        started = time.monotonic()
        result = self.run_fetch()
        self.assertLess(time.monotonic() - started, 10, "Blockierte Quellen duerfen den Lauf nicht aufhalten")

        titles = {j.title: j for j in Job.query.all()}
        self.assertIn("Mediengestalter/in Bild und Ton", titles)
        self.assertNotIn("Kreditorenbuchhalter (m/w/d)", titles)
        self.assertIn("Video Editor (m/w/d)", titles)
        self.assertNotIn("Buchhaltung (m/w/d)", titles)
        self.assertFalse(any("Catering" in t for t in titles))
        self.assertFalse(any(t in ("Postproduktion", "Kamera") for t in titles), "Navigationslinks sind keine Jobs")

        ba = titles["Mediengestalter/in Bild und Ton"]
        self.assertEqual(ba.match_label, "top")
        self.assertEqual(ba.source, "adzuna")
        self.assertEqual(ba.contact_name, "Anna Schmidt")
        self.assertEqual(ba.contact_salutation, "Frau")
        self.assertEqual(ba.contact_email, "bewerbung@beispiel-studios.de")
        self.assertIn("Showreel", ba.application_documents)
        self.assertIn("Schnitt von TV-Beiträgen", ba.tasks)

        setrunner = next(j for t, j in titles.items() if t.startswith("Setrunner"))
        self.assertEqual(setrunner.match_label, "top")

        company_job = titles["Video Editor (m/w/d)"]
        self.assertEqual(company_job.company, "Filmhaus Köln")
        self.assertEqual(company_job.contact_email, "jobs@filmhaus-koeln.de")
        self.assertEqual(company_job.company_website, "https://filmhaus-koeln.de")

        kinds = {r.source: r.kind for r in ScraperRun.query.all()}
        self.assertEqual(kinds["adzuna"], "ok")
        self.assertNotIn("arbeitsagentur", kinds)
        self.assertEqual(kinds["crewunited"], "ok")
        self.assertEqual(kinds["indeed"], "blocked")
        self.assertEqual(kinds["stepstone"], "blocked")
        self.assertEqual(kinds["firma:Filmhaus Köln"], "ok")
        self.assertNotIn("jooble", kinds, "Ohne Schluessel wird Jooble uebersprungen")
        self.assertEqual(result["new_jobs"], Job.query.count())

        # Blockierte Quellen sind kein roter Banner
        from app.status import broken_source_names

        self.assertEqual(broken_source_names(), [])

        # Zweiter Lauf legt nichts doppelt an
        self.assertEqual(self.run_fetch()["new_jobs"], 0)

    def test_error_banner_only_for_active_sources(self):
        db.session.add(CompanySource(name="Kaputt GmbH", career_url="https://kaputt.example/karriere"))
        db.session.commit()
        def get(url, **kwargs):
            if "kaputt.example" in url:
                raise requests.ConnectionError("Name or service not known")
            return fake_get(url, **kwargs)

        with mock.patch.object(http_utils.requests, "get", side_effect=get):
            from app.fetch_jobs import run_fetch_cycle

            run_fetch_cycle(self.app)
        from app.status import broken_source_names

        self.assertIn("firma:Kaputt GmbH", broken_source_names())
        company = CompanySource.query.filter_by(name="Kaputt GmbH").first()
        self.client.post(f"/firmen/{company.id}/delete")
        self.assertNotIn("firma:Kaputt GmbH", broken_source_names())


class RouteTests(AppTestCase):
    def test_pages_render(self):
        for path in ["/", "/archiv", "/unterlagen", "/job/neu", "/firmen", "/einstellungen", "/status", "/status/text"]:
            self.assertEqual(self.client.get(path).status_code, 200, path)

    def test_cross_site_post_blocked(self):
        r = self.client.post("/einstellungen/profil", data={"keywords": "x"}, headers={"Origin": "https://evil.example"})
        self.assertEqual(r.status_code, 403)
        r = self.client.post("/einstellungen/profil", data={"keywords": "Gaffer"}, headers={"Origin": "http://localhost"})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(SearchProfile.query.filter_by(keywords="Gaffer").first())

    def test_settings_keys_and_sources(self):
        self.client.post("/einstellungen/schluessel", data={"adzuna_app_id": "id1", "adzuna_app_key": "k1"})
        self.assertEqual(db.session.get(AppSetting, "adzuna_app_id").value, "id1")
        self.client.post("/einstellungen/schluessel", data={"adzuna_app_id": ""})
        self.assertEqual(db.session.get(AppSetting, "adzuna_app_id").value, "id1", "leeres Feld behaelt den Schluessel")
        before = db.session.get(SourceSetting, "stepstone").enabled
        self.client.post("/einstellungen/quelle/stepstone/toggle")
        db.session.expire_all()
        self.assertNotEqual(db.session.get(SourceSetting, "stepstone").enabled, before)

    def test_manual_add_duplicate_and_status_flow(self):
        data = {"mode": "manual", "title": "Kameraassistent (m/w/d)", "location": "Köln", "url": "https://x.example/job"}
        self.client.post("/job/neu", data=data)
        r = self.client.post("/job/neu", data=data)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Job.query.count(), 1)
        job = Job.query.first()
        self.assertEqual(job.match_label, "top")

        r = self.client.post(f"/job/{job.id}/status", json={"status": "vorbereitung"})
        self.assertEqual(r.get_json(), {"ok": True, "status": "vorbereitung"})
        r = self.client.post(f"/job/{job.id}/status", json={"status": "quatsch"})
        self.assertFalse(r.get_json()["ok"])

        self.client.post(f"/job/{job.id}/save", data={"cover_letter": "Hallo", "company_website": "javascript:alert(1)"})
        db.session.expire_all()
        self.assertEqual(job.cover_letter, "Hallo")
        self.assertEqual(job.company_website, "", "nur http(s)-Links sind erlaubt")

        self.client.post(f"/job/{job.id}/delete", json={})
        db.session.expire_all()
        self.assertEqual(job.status, "archiviert")
        self.client.post(f"/job/{job.id}/purge")
        self.assertEqual(Job.query.count(), 0)

    def test_open_redirect_blocked(self):
        self.client.post("/job/neu", data={"mode": "manual", "title": "Cutter"})
        job = Job.query.first()
        r = self.client.post(f"/job/{job.id}/status", data={"status": "neu", "next": "https://evil.example"})
        self.assertNotIn("evil.example", r.headers["Location"])

    def test_link_import(self):
        page = """<html><head><title>x</title></head><body><script type="application/ld+json">
        {"@type":"JobPosting","title":"Kameraassistent (m/w/d)","hiringOrganization":{"name":"Serien GmbH"},
         "jobLocation":{"address":{"addressLocality":"Köln"}},"description":"&lt;h3&gt;Aufgaben&lt;/h3&gt;&lt;ul&gt;&lt;li&gt;Schärfe ziehen&lt;/li&gt;&lt;/ul&gt;"}
        </script></body></html>"""
        with mock.patch.object(http_utils.requests, "get", return_value=FakeResponse(text=page)):
            r = self.client.post("/job/neu", data={"mode": "link", "url": "https://www.linkedin.com/jobs/view/123"})
        self.assertEqual(r.status_code, 302)
        job = Job.query.first()
        self.assertEqual(job.source, "linkedin")
        self.assertEqual(job.company, "Serien GmbH")
        self.assertEqual(job.url, "https://www.linkedin.com/jobs/view/123")
        self.assertIn("Schärfe ziehen", job.tasks)

    def test_document_upload_with_umlaut_name(self):
        r = self.client.post("/unterlagen/upload", data={"doc_type": "lebenslauf", "file": (io.BytesIO(b"%PDF-1.4"), "Lebenslauf Götze.pdf")},
                             content_type="multipart/form-data")
        self.assertEqual(r.status_code, 302)
        from app.models import Document

        doc = Document.query.first()
        self.assertEqual(doc.filename, "Lebenslauf Götze.pdf")
        response = self.client.get(f"/unterlagen/{doc.id}/download")
        self.assertEqual(response.status_code, 200)
        response.close()


class MigrationTests(unittest.TestCase):
    def test_old_schema_gets_new_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "old.db")
            con = sqlite3.connect(path)
            con.execute("CREATE TABLE jobs (id INTEGER PRIMARY KEY, external_id VARCHAR(64) UNIQUE NOT NULL, "
                        "title VARCHAR(300) NOT NULL, company VARCHAR(200), location VARCHAR(200), url VARCHAR(1000) NOT NULL, "
                        "source VARCHAR(50) NOT NULL, salary VARCHAR(200), description TEXT, posted_at VARCHAR(50), "
                        "fetched_at DATETIME, status VARCHAR(30), notes TEXT, cover_letter TEXT, updated_at DATETIME)")
            con.execute("INSERT INTO jobs (external_id, title, location, url, source, status, cover_letter) "
                        "VALUES ('a', 'Video Editor', 'Köln', 'https://x.example', 'indeed', 'beworben', 'Text')")
            con.commit()
            con.close()

            app = create_app(database_uri=f"sqlite:///{path}")
            with app.app_context():
                job = Job.query.first()
                self.assertEqual(job.cover_letter, "Text")
                self.assertEqual(job.status, "beworben")
                self.assertEqual(job.match_label, "top")
                self.assertEqual(job.tasks, "")
                self.assertEqual(app.test_client().get("/").status_code, 200)
                db.session.remove()
                db.engine.dispose()


if __name__ == "__main__":
    unittest.main()


class OfflineTests(AppTestCase):
    def test_offline_is_not_an_error(self):
        from app.fetch_jobs import run_fetch_cycle
        from app.status import broken_source_names

        with mock.patch.object(http_utils.requests, "get", side_effect=requests.ConnectionError("Name or service not known")):
            result = run_fetch_cycle(self.app)
        self.assertTrue(result["offline"])
        self.assertEqual(broken_source_names(), [])
        runs = ScraperRun.query.filter_by(source="adzuna").all()
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0].kind, "offline")
        self.assertIn("uebersprungen".replace("ue", "ü"), runs[0].message, "nach dem ersten Verbindungsfehler abbrechen")

    def test_single_dead_source_is_an_error(self):
        from app.fetch_jobs import run_fetch_cycle
        from app.status import broken_source_names

        def get(url, **kwargs):
            if "crew-united" in url:
                raise requests.ConnectionError("Name or service not known")
            return fake_get(url, **kwargs)

        with mock.patch.object(http_utils.requests, "get", side_effect=get):
            result = run_fetch_cycle(self.app)
        self.assertFalse(result["offline"])
        self.assertEqual(broken_source_names(), ["crewunited"])


class WorkflowTests(AppTestCase):
    def _job(self, **kwargs):
        from app.fetch_jobs import job_from_listing
        from app.scrapers.base import JobListing

        listing = JobListing(title=kwargs.pop("title", "Kameraassistent (m/w/d)"), url="https://x.example/j1",
                             source=kwargs.pop("source", "crewunited"), company="Serienwerk GmbH", location="Köln")
        job = job_from_listing(listing, None, 1.0, "top", "")
        for key, value in kwargs.items():
            setattr(job, key, value)
        db.session.add(job)
        db.session.commit()
        return job

    def test_cover_letter_template_is_filled(self):
        from app.letters import fill_template

        job = self._job(contact_name="Anna Schmidt", contact_salutation="Frau")
        text = fill_template("{anrede}\n{anrede_du}\nBewerbung als {stelle} bei {firma} {quelle}.", job)
        self.assertIn("Sehr geehrte Frau Schmidt,", text)
        self.assertIn("Hallo Anna,", text)
        self.assertIn("Bewerbung als Kameraassistent bei Serienwerk GmbH auf Crew United", text, "(m/w/d) entfernt")
        job.contact_name, job.contact_salutation = "", ""
        self.assertIn("Sehr geehrte Damen und Herren,", fill_template("{anrede}", job))

        page = self.client.get(f"/job/{job.id}").get_data(as_text=True)
        self.assertIn("Vorlage einfügen", page, "Standard-Vorlage wird beim Start angelegt")

    def test_applied_sets_follow_up_and_checklist(self):
        from datetime import date, timedelta

        job = self._job(application_documents="Lebenslauf, Showreel / Arbeitsproben")
        self.client.post(f"/job/{job.id}/save", data={"docs_checklist_present": "1", "docs_done": ["Lebenslauf", "Erfunden"]})
        db.session.expire_all()
        self.assertEqual(job.docs_done_list(), ["Lebenslauf"])
        self.assertEqual(job.docs_progress(), (1, 2))

        self.client.post(f"/job/{job.id}/status", json={"status": "beworben"})
        db.session.expire_all()
        self.assertEqual(job.applied_at, date.today())
        self.assertEqual(job.follow_up_at, date.today() + timedelta(days=14))
        self.assertFalse(job.follow_up_due())

        job.follow_up_at = date.today() - timedelta(days=1)
        db.session.commit()
        self.assertIn("Nachfassen fällig", self.client.get("/").get_data(as_text=True))
        self.client.post(f"/job/{job.id}/nachgefasst")
        db.session.expire_all()
        self.assertIsNone(job.follow_up_at)
        self.assertIn("nachgefasst", job.notes)

    def test_deadline_state(self):
        from datetime import date, timedelta

        job = self._job(deadline=date.today() + timedelta(days=3))
        self.assertEqual(job.deadline_state(), "bald")
        job.deadline = date.today() - timedelta(days=1)
        self.assertEqual(job.deadline_state(), "abgelaufen")
        job.status = "beworben"
        self.assertEqual(job.deadline_state(), "")

    def test_company_suggestions(self):
        from app.company_suggestions import SUGGESTED_COMPANIES

        page = self.client.get("/firmen").get_data(as_text=True)
        self.assertIn("MMC Studios Köln", page)
        self.client.post("/firmen/vorschlaege", data={"name": "MMC Studios Köln"})
        self.assertEqual(CompanySource.query.count(), 1)
        self.client.post("/firmen/vorschlaege")
        self.assertEqual(CompanySource.query.count(), len(SUGGESTED_COMPANIES))
        self.client.post("/firmen/vorschlaege")
        self.assertEqual(CompanySource.query.count(), len(SUGGESTED_COMPANIES), "keine Duplikate")

    def test_new_top_jobs_trigger_notification(self):
        from app import fetch_runner

        SearchProfile.query.delete()
        db.session.add(SearchProfile(keywords="Mediengestalter", location="Köln", radius_km=25))
        db.session.commit()
        with mock.patch.object(http_utils.requests, "get", side_effect=fake_get), \
                mock.patch.object(fetch_runner, "notify_new_top_jobs") as notify:
            self.assertTrue(fetch_runner.start_async(self.app))
            for _ in range(100):
                if not fetch_runner.state["running"]:
                    break
                time.sleep(0.05)
        titles = notify.call_args[0][0]
        self.assertIn("Mediengestalter/in Bild und Ton", titles)
        self.assertNotIn("Kreditorenbuchhalter (m/w/d)", titles)


class CrewUnitedDiagnosisTests(AppTestCase):
    def test_unknown_layout_reports_link_paths(self):
        from app.scrapers import crewunited

        page = '<html><head><title>Jobs | Crew United</title></head><body><a href="/de/Jobboerse/Angebot_123.html">Kamera</a><a href="/de/login">Login</a></body></html>'
        with mock.patch.object(http_utils.requests, "get", side_effect=lambda url, **kw: FakeResponse(404) if url.endswith("robots.txt") else FakeResponse(text=page)):
            with self.assertRaises(Exception) as ctx:
                crewunited.search({}, {"http_timeout_seconds": 5})
        message = str(ctx.exception)
        self.assertIn("/de/Jobboerse/Angebot_123.html", message)
        self.assertIn("Login-Hinweis=ja", message)

    def test_removed_source_is_cleaned_up(self):
        from app.db_setup import seed_defaults
        from app.status import latest_run_per_source

        db.session.add(SourceSetting(name="arbeitsagentur", enabled=True))
        db.session.add(ScraperRun(source="arbeitsagentur", ok=False, kind="blocked", message="403"))
        db.session.commit()
        seed_defaults()
        self.assertIsNone(db.session.get(SourceSetting, "arbeitsagentur"))
        self.assertNotIn("arbeitsagentur", latest_run_per_source())


LINKEDIN_ALERT = """<html><body><table>
<tr><td><a href="https://www.linkedin.com/comm/jobs/view/4012345678/?trackingId=abc&refId=x"><img src="logo.png"></a></td>
<td><a href="https://www.linkedin.com/comm/jobs/view/4012345678/?trackingId=abc">Kameraassistent (m/w/d)</a><br>
Serienwerk GmbH<br>Köln, Nordrhein-Westfalen</td></tr>
<tr><td><a href="https://www.linkedin.com/comm/jobs/view/4099999999/">Kreditorenbuchhalter (m/w/d)</a><br>Zahlen AG<br>Köln</td></tr>
<tr><td><a href="https://www.linkedin.com/comm/jobs/view/4088888888/">Ansehen</a>
<div>Video Editor (m/w/d)<br>Agentur Rot<br>Hürth</div></td></tr>
<tr><td><a href="https://www.linkedin.com/comm/mynetwork/">Dein Netzwerk</a></td></tr>
</table></body></html>"""

INDEED_ALERT = """<html><body>
<a href="https://de.indeed.com/rc/clk/dl?jk=0123456789abcdef&from=ja&tk=zzz">Setrunner (m/w/d)</a>
<div>Filmproduktion Nord - Hamburg - Drehtage im Oktober</div>
<a href="https://click.example-mail.com/track?url=https%3A%2F%2Fde.indeed.com%2Fviewjob%3Fjk%3Dfedcba9876543210">Cutter (m/w/d)</a>
</body></html>"""

STEPSTONE_TEXT_ALERT = """Neue Jobs fuer dich:
Mediengestalter Bild und Ton (m/w/d)
https://www.stepstone.de/stellenangebote--Mediengestalter-Bild-und-Ton-Koeln-Studio-GmbH--12345678-inline.html?cid=mail
"""


class MailAlertTests(AppTestCase):
    def test_parse_linkedin_alert(self):
        from app.scrapers.mail_alerts import listings_from_html

        jobs = {j.url: j for j in listings_from_html(LINKEDIN_ALERT)}
        self.assertEqual(len(jobs), 3, "Bild- und Titel-Link derselben Stelle = 1 Job, Netzwerk-Link ignoriert")
        cam = jobs["https://www.linkedin.com/jobs/view/4012345678/"]
        self.assertEqual(cam.title, "Kameraassistent (m/w/d)")
        self.assertEqual(cam.company, "Serienwerk GmbH")
        self.assertEqual(cam.location, "Köln, Nordrhein-Westfalen")
        self.assertEqual(cam.source, "linkedin")
        editor = jobs["https://www.linkedin.com/jobs/view/4088888888/"]
        self.assertEqual(editor.title, "Video Editor (m/w/d)", "Generischer Linktext -> Titel aus dem Umfeld")

    def test_parse_indeed_and_tracking_redirect(self):
        from app.scrapers.mail_alerts import listings_from_html

        urls = {j.url: j.title for j in listings_from_html(INDEED_ALERT)}
        self.assertEqual(urls["https://de.indeed.com/viewjob?jk=0123456789abcdef"], "Setrunner (m/w/d)")
        self.assertEqual(urls["https://de.indeed.com/viewjob?jk=fedcba9876543210"], "Cutter (m/w/d)")

    def _fake_imap(self, messages):
        from email.message import EmailMessage

        raw = []
        for sender, html, plain in messages:
            msg = EmailMessage()
            msg["From"] = sender
            msg["Subject"] = "Neue Jobs"
            if plain:
                msg.set_content(html)
            else:
                msg.set_content("Text")
                msg.add_alternative(html, subtype="html")
            raw.append(msg.as_bytes())

        client = mock.MagicMock()
        client.select.return_value = ("OK", [b"3"])
        client.search.side_effect = lambda *args: ("OK", [b"1 2 3"] if args[-1] == '"linkedin.com"' else [b""])
        client.fetch.side_effect = lambda msg_id, spec: ("OK", [(b"x", raw[int(msg_id) - 1])])
        return client

    def test_full_cycle_from_mailbox(self):
        from app.fetch_jobs import run_fetch_cycle

        for key, value in (("mail_address", "ich@example.de"), ("mail_password", "app-pass"), ("mail_provider", "gmx")):
            db.session.add(AppSetting(key=key, value=value))
        db.session.commit()
        client = self._fake_imap([
            ("LinkedIn <jobs-noreply@linkedin.com>", LINKEDIN_ALERT, False),
            ("Indeed <alert@indeed.com>", INDEED_ALERT, False),
            ("StepStone <noreply@stepstone.de>", STEPSTONE_TEXT_ALERT, True),
        ])
        requested = []

        def get(url, **kwargs):
            requested.append(url)
            return fake_get(url, **kwargs)

        with mock.patch("app.scrapers.mail_alerts.imaplib.IMAP4_SSL", return_value=client) as ssl, \
                mock.patch.object(http_utils.requests, "get", side_effect=get):
            run_fetch_cycle(self.app)

        ssl.assert_called_once()
        self.assertEqual(ssl.call_args[0][0], "imap.gmx.net")
        client.select.assert_called_with("INBOX", readonly=True)
        self.assertTrue(all("PEEK" in c.args[1] for c in client.fetch.call_args_list), "Mails nie als gelesen markieren")

        titles = {j.title: j for j in Job.query.all()}
        self.assertIn("Kameraassistent (m/w/d)", titles)
        self.assertIn("Setrunner (m/w/d)", titles)
        self.assertIn("Mediengestalter Bild und Ton (m/w/d)", titles)
        self.assertNotIn("Kreditorenbuchhalter (m/w/d)", titles)
        self.assertEqual(titles["Kameraassistent (m/w/d)"].match_label, "top")
        self.assertFalse(any("linkedin.com" in u or "indeed.com/viewjob" in u or "stepstone.de/stellen" in u for u in requested),
                         "Portal-Detailseiten werden nicht automatisch abgerufen")
        self.assertEqual(ScraperRun.query.filter_by(source="mail_alerts").first().kind, "ok")

    def test_wrong_password_is_config_hint(self):
        import imaplib

        from app.scrapers import mail_alerts
        from app.scrapers.base import ScraperError

        client = mock.MagicMock()
        client.login.side_effect = imaplib.IMAP4.error("AUTHENTICATIONFAILED")
        with mock.patch("app.scrapers.mail_alerts.imaplib.IMAP4_SSL", return_value=client):
            with self.assertRaises(ScraperError) as ctx:
                mail_alerts.search({}, {"mail_address": "a@b.de", "mail_password": "x"})
        self.assertEqual(ctx.exception.kind, "config")
        self.assertIn("App-Passwort", str(ctx.exception))

    def test_settings_page_saves_mail(self):
        self.client.post("/einstellungen/mail", data={"mail_provider": "icloud", "mail_address": "ich@icloud.com",
                                                      "mail_password": "abcd efgh ijkl mnop", "action": "save"})
        self.assertEqual(db.session.get(AppSetting, "mail_password").value, "abcdefghijklmnop")
        page = self.client.get("/einstellungen").get_data(as_text=True)
        self.assertIn("Job-Alarme per E-Mail", page)
        self.assertNotIn("abcdefghijklmnop", page, "Passwort nie im HTML ausgeben")
