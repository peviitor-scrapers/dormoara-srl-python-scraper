"""
DORMOARA S.R.L. ANOFM Scraper

Collects job postings published by DORMOARA S.R.L. (CUI 52632530) on ANOFM
(mediere.anofm.ro) and publishes them to peviitor.ro via the v1 API.
"""

import datetime
import json
import pathlib
import sys
import time

from .anaf import search_anofm
from .api import delete_job_by_url, delete_jobs_by_cif, query_solr, upsert_company, upsert_jobs
from .company import validate_and_get_company
from .config import company_config, scraper_config
from .markdown_generator import generate_jobs_markdown

COMPANY_CIF = company_config["id"]
JOB_DETAILS_PREFIX = scraper_config["jobDetailsPrefix"]
COMPANY_NAME = None


def map_to_job_model(raw_job, cif, company_name=None):
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    job = {
        "url": raw_job["url"],
        "title": raw_job["title"],
        "company": company_name or COMPANY_NAME,
        "cif": cif,
        "date": raw_job.get("date") or now,
        "status": "scraped",
    }
    if raw_job.get("location"):
        job["location"] = raw_job["location"]
    return job


def transform_jobs_for_solr(payload):
    company = (payload.get("company") or "").upper()
    jobs = []
    for job in payload.get("jobs", []):
        locations = [loc for loc in (job.get("location") or []) if loc]
        jobs.append({**job, "location": locations or ["România"]})
    return {**payload, "company": company, "jobs": jobs}


def _validated_company():
    try:
        return validate_and_get_company()
    except Exception as err:
        print(f"ANAF validation failed ({err}) — using config identity")
        return {
            "cif": company_config["id"],
            "company": company_config["company"],
            "status": "active",
            "address": (company_config.get("location") or ["România"])[0],
        }


def main(root=None):
    root = root or pathlib.Path(__file__).resolve().parents[1]

    print("=== Step 1: Get existing jobs from SOLR ===")
    existing_result = query_solr(COMPANY_CIF)
    existing_count = existing_result["numFound"]
    existing_urls = {doc.get("url") for doc in existing_result["docs"]
                     if doc.get("url") and doc["url"].startswith(JOB_DETAILS_PREFIX)}
    print(f"Found {existing_count} existing jobs in SOLR ({len(existing_urls)} from ANOFM)")

    print("=== Step 2: Validate company via ANAF ===")
    validated = _validated_company()
    global COMPANY_NAME
    COMPANY_NAME = validated["company"]
    if validated.get("status") == "inactive":
        print("Company is INACTIVE — deleting jobs and skipping scrape.")
        try:
            delete_jobs_by_cif(validated["cif"])
        except Exception as err:
            print(f"Failed to delete jobs: {err}")
        return

    try:
        upsert_company({
            "id": validated["cif"],
            "company": validated["company"],
            "brand": company_config.get("brand"),
            "status": "activ",
            "location": [validated["address"]] if validated.get("address") else company_config["location"],
            "website": company_config.get("website"),
            "career": company_config.get("career"),
            "scraperFile": company_config.get("scraperFile"),
            "lastScraped": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d"),
        })
    except Exception as err:
        print(f"Note: Could not upsert company: {err}")

    print("=== Step 3: Scrape DORMOARA S.R.L. jobs from ANOFM ===")
    raw_jobs = search_anofm(validated["cif"])
    print(f"Jobs scraped from ANOFM: {len(raw_jobs)}")

    jobs = [map_to_job_model(job, validated["cif"]) for job in raw_jobs]
    payload = {
        "source": "mediere.anofm.ro",
        "scrapedAt": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "company": COMPANY_NAME,
        "cif": validated["cif"],
        "jobs": jobs,
    }

    transformed = transform_jobs_for_solr(payload)
    print(f"Jobs with valid locations: {len(transformed['jobs'])}")

    jobs_path = root / "scraper" / "jobs.json"
    jobs_path.parent.mkdir(parents=True, exist_ok=True)
    jobs_path.write_text(json.dumps(transformed, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Saved scraper/jobs.json")

    company_data = {
        "id": validated["cif"],
        "company": transformed["company"],
        "brand": company_config.get("brand"),
        "status": "activ",
        "location": [validated["address"]] if validated.get("address") else company_config["location"],
        "website": company_config.get("website"),
        "career": company_config.get("career"),
        "lastScraped": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d"),
    }
    markdown = generate_jobs_markdown(company_data, transformed["jobs"])
    (root / "docs").mkdir(exist_ok=True)
    (root / "docs" / "jobs.md").write_text(markdown, encoding="utf-8")
    print("Saved docs/jobs.md")

    src_company = pathlib.Path(__file__).resolve().parent / "config" / "company.json"
    (root / "docs" / "company.json").write_text(src_company.read_text(encoding="utf-8"), encoding="utf-8")

    print("\n=== Step 4: Upsert jobs to SOLR ===")
    upsert_jobs(transformed["jobs"])

    scraped_urls = {job["url"] for job in transformed["jobs"]}
    stale_urls = [url for url in existing_urls if url not in scraped_urls]
    if stale_urls:
        print(f"\n=== Step 4.5: Delete {len(stale_urls)} stale job(s) ===")
        for url in stale_urls:
            try:
                delete_job_by_url(url)
            except Exception as err:
                print(f"  Failed to delete: {url} — {err}")
    else:
        print("\nNo stale jobs to delete")

    print("\n=== Step 5: Summary ===")
    time.sleep(2)
    final_result = query_solr(COMPANY_CIF)
    print(f"Jobs existing in SOLR before scrape: {existing_count}")
    print(f"Jobs scraped from ANOFM: {len(transformed['jobs'])}")
    print(f"Stale jobs attempted: {len(stale_urls)}")
    print(f"Jobs in SOLR after scrape: {final_result['numFound']}")


if __name__ == "__main__":
    try:
        main()
    except Exception as err:
        print("Scraper failed:", err)
        sys.exit(1)
