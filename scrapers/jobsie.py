import hashlib
import logging
import time
from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup

from .base import Job

logger = logging.getLogger(__name__)

BASE_URL = "https://www.jobs.ie"
SEARCH_URL = f"{BASE_URL}/jobs/search/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def _job_id(url: str) -> str:
    return "jobsie_" + hashlib.md5(url.encode()).hexdigest()[:12]


def _parse_posted(text: str) -> str:
    now = datetime.now(timezone.utc)
    text = text.strip().lower()
    try:
        if "today" in text or "just" in text or "hour" in text:
            if "hour" in text:
                n = int("".join(c for c in text if c.isdigit()) or "1")
                return (now - timedelta(hours=n)).isoformat()
            return now.isoformat()
        if "yesterday" in text:
            return (now - timedelta(days=1)).isoformat()
        if "day" in text:
            n = int("".join(c for c in text if c.isdigit()) or "1")
            return (now - timedelta(days=n)).isoformat()
    except Exception:
        pass
    return now.isoformat()


def _is_within_24h(posted_at_iso: str) -> bool:
    try:
        posted = datetime.fromisoformat(posted_at_iso)
        if posted.tzinfo is None:
            posted = posted.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - posted <= timedelta(hours=24)
    except Exception:
        return True


def search(keywords: list[str], location: str = "Ireland", max_results: int = 20) -> list[Job]:
    jobs = []
    seen_ids = set()

    for keyword in keywords:
        logger.info(f"Jobs.ie: searching '{keyword}'")
        params = {"q": keyword, "l": location, "sort": "date"}
        try:
            resp = requests.get(SEARCH_URL, params=params, headers=HEADERS, timeout=20)
            soup = BeautifulSoup(resp.text, "html.parser")

            # Jobs.ie listing cards
            cards = soup.select("article.job-item, div.job-listing, li.job-result")
            if not cards:
                # Try alternate selector patterns
                cards = soup.select("[data-job-id], .job-card, .listing")

            for card in cards[:max_results]:
                try:
                    title_el = card.select_one("h2 a, h3 a, .job-title a, a.job-link")
                    company_el = card.select_one(".company, .employer, .company-name")
                    location_el = card.select_one(".location, .job-location")
                    date_el = card.select_one(".date, .posted-date, time, .age")

                    if not title_el:
                        continue

                    title = title_el.get_text(strip=True)
                    url = title_el.get("href", "")
                    if url and not url.startswith("http"):
                        url = BASE_URL + url

                    if not url:
                        continue

                    job_id = _job_id(url)
                    if job_id in seen_ids:
                        continue
                    seen_ids.add(job_id)

                    company = company_el.get_text(strip=True) if company_el else "Unknown"
                    loc = location_el.get_text(strip=True) if location_el else location
                    date_text = date_el.get_text(strip=True) if date_el else "today"
                    posted_at = _parse_posted(date_text)

                    if not _is_within_24h(posted_at):
                        continue

                    # Fetch description from job page
                    try:
                        jresp = requests.get(url, headers=HEADERS, timeout=15)
                        jsoup = BeautifulSoup(jresp.text, "html.parser")
                        desc_el = jsoup.select_one(".job-description, #job-description, .description")
                        description = desc_el.get_text(separator="\n", strip=True)[:4000] if desc_el else ""
                    except Exception:
                        description = ""

                    jobs.append(Job(
                        id=job_id,
                        platform="jobs.ie",
                        title=title,
                        company=company,
                        location=loc,
                        url=url,
                        description=description,
                        posted_at=posted_at,
                    ))
                    time.sleep(1)

                except Exception as e:
                    logger.warning(f"Jobs.ie: error parsing card: {e}")

        except Exception as e:
            logger.error(f"Jobs.ie search error for '{keyword}': {e}")

        time.sleep(3)

    return jobs
