# MAINTENANCE

## Issue-driven maintenance

Before any work, check open issues and fix them:

```bash
gh issue list --repo peviitor-scrapers/dormoara-srl-python-scraper --state open
```

Prioritize `critical` → `bug` → `enhancement` → `documentation`. For each
open issue: read it, investigate the root cause, apply the fix, run the
relevant tests, commit with the issue reference (e.g. `fix: resolve #20`),
push, then close the issue with a comment linking the commit.

If an issue cannot be resolved (external API down, ANOFM unreachable), add
a comment explaining the blocker, label it `wontfix`/`question` as
appropriate, and move on.

## Routine

- The scheduled `job-seeker-ro-spider.yml` workflow scrapes daily.
- If the scrape fails, check: ANOFM reachability, ANAF API status, API response.
- Validate job URLs periodically:

```bash
python3 -m scraper.validate_jobs 52632530 --mode content --dry-run
python3 -m scraper.validate_jobs 52632530 --mode content --delete
```

## ANOFM response changes

If `search_anofm` returns 0 or few jobs, inspect the API response:

```bash
curl -s -X POST "https://mediere.anofm.ro/api/entity/vw_public_job_posting" \
  -H "Content-Type: application/json" \
  -d '{"current":1,"rowCount":250,"sort":{"created_at":"desc"},"employer_tax_code":"52632530"}'
```

Adjust `search_anofm` in `scraper/anaf.py` and the expected count in
`tests/e2e/test_scraper.py`.

## Company data changes

Edit `scraper/config/company.json` only. Run the scraper to regenerate
`docs/company.json`.

## ANAF outages

`get_company_from_anaf` falls back demoanaf.ro → cuiscan.ro → cache
(`scraper/anaf_cache.json`). If all fail, the scraper errors clearly.
