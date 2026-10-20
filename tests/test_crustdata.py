"""Crustdata helpers (no live network)."""
from applyforme.crustdata import careers_url_from_website, job_from_listing, parse_company_data


def test_careers_url():
    assert careers_url_from_website("https://stripe.com") == "https://stripe.com/careers"
    assert careers_url_from_website("stripe.com").endswith("/careers")
    assert careers_url_from_website("") == ""


def test_parse_company_data():
    info = parse_company_data({
        "basic_info": {
            "company_name": "Acme",
            "website": "https://acme.test",
            "professional_network_url": "https://linkedin.com/company/acme",
            "primary_domain": "acme.test",
            "industry": "Software",
        },
        "hiring": {
            "openings_count": 12,
            "recent_openings": [{"title": "SWE", "url": "https://jobs.acme.test/1", "location_text": "Remote"}],
        },
        "headcount": {"linkedin_headcount": 200},
        "funding": {"last_round_type": "series_b"},
    })
    assert info["name"] == "Acme"
    assert info["careers_url"] == "https://acme.test/careers"
    assert info["openings_count"] == 12
    assert info["recent_openings"][0]["url"].startswith("https://jobs")


def test_job_from_listing_surfaces_posting_url():
    j = job_from_listing({
        "crustdata_job_id": 99,
        "job_details": {"title": "Backend Engineer", "url": "https://boards.greenhouse.io/x/jobs/1", "source": "greenhouse"},
        "company": {"basic_info": {"company_name": "X", "website": "https://x.com", "primary_domain": "x.com"}},
        "location": {"city": "Bengaluru", "country": "India"},
        "content": {"description": "Build APIs"},
    })
    assert j is not None
    assert j.url == "https://boards.greenhouse.io/x/jobs/1"
    assert j.apply_url == j.url
    assert j.careers_url == "https://x.com/careers"
    assert j.id == "crustdata:99"
