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


def test_main_writes_summary(tmp_path, monkeypatch):
    fake_jobs = [
        {"url": f"https://mediere.anofm.ro/app/module/mediere/job/{i}",
         "title": f"Job {i}", "location": ["Sfântu Gheorghe"]}
        for i in range(3)
    ]
    monkeypatch.setattr(index, "query_solr", lambda cif: {"numFound": 0, "docs": []})
    monkeypatch.setattr(index, "upsert_jobs", lambda jobs: None)
    monkeypatch.setattr(index, "delete_job_by_url", lambda url: None)
    monkeypatch.setattr(index, "upsert_company", lambda cfg: None)
    monkeypatch.setattr(index, "validate_and_get_company", lambda: {
        "company": "DORMOARA S.R.L.", "cif": "52632530", "status": "active",
        "address": "SFÂNTU GHEORGHE"})
    monkeypatch.setattr(index, "search_anofm", lambda cif: fake_jobs)
    monkeypatch.setattr(index.time, "sleep", lambda s: None)

    index.main(root=tmp_path)

    out = tmp_path / "scraper" / "jobs.json"
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert len(data["jobs"]) == 3
    assert data["company"] == "DORMOARA S.R.L."
    assert (tmp_path / "docs" / "jobs.md").exists()


def test_main_inactive_company_skips_scrape(tmp_path, monkeypatch):
    deleted = []
    monkeypatch.setattr(index, "query_solr", lambda cif: {"numFound": 1, "docs": []})
    monkeypatch.setattr(index, "validate_and_get_company", lambda: {
        "company": "DORMOARA S.R.L.", "cif": "52632530", "status": "inactive"})
    monkeypatch.setattr(index, "delete_jobs_by_cif", lambda cif: deleted.append(cif))
    monkeypatch.setattr(index, "search_anofm",
                        lambda cif: (_ for _ in ()).throw(AssertionError("should not scrape")))

    index.main(root=tmp_path)

    assert deleted == ["52632530"]
