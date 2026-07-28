import hashlib
import json
import logging
import re
import time
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

from .base import Job

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IE,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


def _job_id(jk: str) -> str:
    return "indeed_" + hashlib.md5(jk.encode()).hexdigest()[:12]


def _parse_relative_date(text: str) -> str:
    now = datetime.now(timezone.utc)
    text = text.lower().strip()
    try:
        if "just" in text or "minute" in text:
            return now.isoformat()
        if "hour" in text:
            n = int(re.search(r'\d+', text).group()) if re.search(r'\d+', text) else 1
            return (now - timedelta(hours=n)).isoformat()
        if "day" in text:
            n = int(re.search(r'\d+', text).group()) if re.search(r'\d+', text) else 1
            return (now - timedelta(days=n)).isoformat()
        if "today" in text:
            return now.isoformat()
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


def _fetch_jobs_for_keyword(session: requests.Session, keyword: str, location: str, max_results: int) -> list[Job]:
    jobs = []
    params = {
        "q": keyword,
        "l": location,
        "sort": "date",
        "fromage": "1",
        "start": 0,
    }
    url = "https://www.indeed.com/jobs?" + urlencode(params)

    try:
        resp = session.get(url, timeout=20)
        if resp.status_code != 200:
            logger.warning(f"Indeed returned {resp.status_code} for '{keyword}'")
            return []

        # Method 1: Extract from mosaic JSON
        match = re.search(
            r'window\.mosaic\.providerData\["mosaic-provider-jobcards"\]\s*=\s*(\{.*?\});',
            resp.text, re.DOTALL
        )
        if match:
            try:
                data = json.loads(match.group(1))
                results = (
                    data.get("metaData", {})
                    .get("mosaicProviderJobCardsModel", {})
                    .get("results", [])
                )
                for item in results[:max_results]:
                    jk = item.get("jobkey", "")
                    if not jk:
                        continue
                    posted_text = item.get("formattedRelativeTime", "today")
                    posted_at = _parse_relative_date(posted_text)
                    if not _is_within_24h(posted_at):
                        continue
                    jobs.append(Job(
                        id=_job_id(jk),
                        platform="indeed",
                        title=item.get("displayTitle") or item.get("title", "Unknown"),
                        company=item.get("company", "Unknown"),
                        location=item.get("jobLocationCity") or item.get("formattedLocation") or location,
                        url=f"https://www.indeed.com/viewjob?jk={jk}",
                        description=BeautifulSoup(
                            item.get("snippet", ""), "html.parser"
                        ).get_text(separator="\n", strip=True),
                        posted_at=posted_at,
                    ))
                if jobs:
                    return jobs
            except (json.JSONDecodeError, KeyError) as e:
                logger.debug(f"Indeed JSON parse failed: {e}")

        # Method 2: Fall back to HTML card parsing
        soup = BeautifulSoup(resp.text, "html.parser")
        cards = soup.select("[data-jk]")
        for card in cards[:max_results]:
            jk = card.get("data-jk", "")
            if not jk:
                continue
            title_el = card.select_one("h2 span[title], h2 a span, .jobTitle span")
            company_el = card.select_one('[data-testid="company-name"], .companyName')
            date_el = card.select_one('[data-testid="myJobsStateDate"], span.date')
            title = title_el.get("title") or title_el.get_text(strip=True) if title_el else "Unknown"
            company = company_el.get_text(strip=True) if company_el else "Unknown"
            posted_text = date_el.get_text(strip=True) if date_el else "today"
            posted_at = _parse_relative_date(posted_text)
            if not _is_within_24h(posted_at):
                continue
            jobs.append(Job(
                id=_job_id(jk),
                platform="indeed",
                title=title,
                company=company,
                location=location,
                url=f"https://www.indeed.com/viewjob?jk={jk}",
                description="",
                posted_at=posted_at,
            ))

    except Exception as e:
        logger.error(f"Indeed fetch error for '{keyword}': {e}")

    return jobs


def search(keywords: list[str], location: str = "Ireland", max_results: int = 20) -> list[Job]:
    session = requests.Session()
    session.headers.update(HEADERS)

    # Warm up session with a homepage visit to get cookies
    try:
        session.get("https://www.indeed.com/", timeout=10)
        time.sleep(1)
    except Exception:
        pass

    all_jobs = []
    seen_ids = set()

    for keyword in keywords:
        logger.info(f"Indeed: searching '{keyword}' in {location}")
        jobs = _fetch_jobs_for_keyword(session, keyword, location, max_results)
        for job in jobs:
            if job.id not in seen_ids:
                seen_ids.add(job.id)
                all_jobs.append(job)
        time.sleep(2)

    return all_jobs
