"""Unit tests for the ANOFM-only index pipeline."""

import json

from scraper import index


def test_map_to_job_model_adds_company_and_status():
    index.COMPANY_NAME = "DORMOARA S.R.L."
    raw = {
        "url": "https://mediere.anofm.ro/app/module/mediere/job/1",
        "title": "Lucrător comercial",
        "location": ["Sfântu Gheorghe"],
    }
    job = index.map_to_job_model(raw, "52632530")
    assert job["company"] == "DORMOARA S.R.L."
    assert job["cif"] == "52632530"
    assert job["status"] == "scraped"
    assert job["location"] == ["Sfântu Gheorghe"]
    assert job["date"]


def test_map_to_job_model_without_location():
    raw = {"url": "https://mediere.anofm.ro/app/module/mediere/job/2",
           "title": "Vânzător"}
    job = index.map_to_job_model(raw, "52632530", company_name="DORMOARA S.R.L.")
    assert "location" not in job


def test_transform_jobs_for_solr_uppercases_company():
    jobs = [{"url": "https://x/job", "title": "Test", "location": ["Cluj-Napoca"]}]
    transformed = index.transform_jobs_for_solr({"company": "Dormoara S.R.L.", "jobs": jobs})
    assert transformed["company"] == "DORMOARA S.R.L."
    assert transformed["jobs"][0]["location"] == ["Cluj-Napoca"]


def test_transform_jobs_for_solr_location_fallback():
    jobs = [{"url": "https://x/job", "title": "Test", "location": []}]
    transformed = index.transform_jobs_for_solr({"company": "DORMOARA S.R.L.", "jobs": jobs})
    assert transformed["jobs"][0]["location"] == ["România"]


def test_transform_jobs_for_solr_missing_location_fallback():
    jobs = [{"url": "https://x/job", "title": "Test"}]
    transformed = index.transform_jobs_for_solr({"company": "DORMOARA S.R.L.", "jobs": jobs})
    assert transformed["jobs"][0]["location"] == ["România"]


def _stub_main(monkeypatch, tmp_path, raw_jobs):
    monkeypatch.setattr(index, "query_solr", lambda cif: {"numFound": 0, "docs": []})
    monkeypatch.setattr(index, "upsert_jobs", lambda jobs: None)
    monkeypatch.setattr(index, "delete_job_by_url", lambda url: None)
    monkeypatch.setattr(index, "upsert_company", lambda cfg: None)
    monkeypatch.setattr(index, "validate_and_get_company", lambda: {
        "company": "DORMOARA S.R.L.", "cif": "52632530", "address": "SFÂNTU GHEORGHE"})
    monkeypatch.setattr(index, "search_anofm", lambda cif: raw_jobs)
    monkeypatch.setattr(index, "drop_dead_urls", lambda jobs: jobs)
    return tmp_path


def test_main_writes_summary(tmp_path, monkeypatch):
    fake_jobs = [
        {"url": f"https://mediere.anofm.ro/app/module/mediere/job/{i}",
         "title": f"Job {i}", "location": ["Sfântu Gheorghe"]}
        for i in range(3)
    ]
    root = _stub_main(monkeypatch, tmp_path, fake_jobs)

    index.main(root=root)

    out = tmp_path / "scraper" / "jobs.json"
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert len(data["jobs"]) == 3
    assert data["company"] == "DORMOARA S.R.L."
    assert (tmp_path / "docs" / "jobs.md").exists()


def test_main_dedupes_anofm_urls(tmp_path, monkeypatch):
    job = {"url": "https://mediere.anofm.ro/app/module/mediere/job/1", "title": "Job"}
    root = _stub_main(monkeypatch, tmp_path, [job, dict(job)])

    index.main(root=root)

    data = json.loads((tmp_path / "scraper" / "jobs.json").read_text(encoding="utf-8"))
    assert len(data["jobs"]) == 1


def test_main_canary_aborts_before_any_write(tmp_path, monkeypatch):
    upserted = []
    root = _stub_main(monkeypatch, tmp_path, [])
    monkeypatch.setattr(index, "upsert_jobs", lambda jobs: upserted.append(jobs))
    monkeypatch.setattr(index, "upsert_company", lambda cfg: (_ for _ in ()).throw(AssertionError("no write")))

    index.main(root=root)

    assert upserted == []
    assert not (tmp_path / "scraper" / "jobs.json").exists()


def test_drop_dead_urls_drops_soft_404(monkeypatch):
    good = {"url": "https://x/good", "title": "Good"}
    old = {"url": "https://x/old", "title": "Old"}
    monkeypatch.setattr(index, "validate_by_content", lambda url: {
        "url": url, "status": "active" if url.endswith("good") else "expired",
        "http_status": 200, "error": None})

    assert index.drop_dead_urls([good, old]) == [good]
