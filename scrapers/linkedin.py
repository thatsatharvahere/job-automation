import hashlib
import time
import logging
from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup

from .base import Job

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# LinkedIn guest jobs API — no auth required
SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"


def _make_job_id(url: str) -> str:
    return "linkedin_" + hashlib.md5(url.encode()).hexdigest()[:12]


def _parse_posted_time(time_str: str) -> str:
    """Convert LinkedIn relative time to ISO 8601."""
    now = datetime.now(timezone.utc)
    time_str = time_str.strip().lower()
    try:
        if "minute" in time_str:
            n = int(time_str.split()[0]) if time_str[0].isdigit() else 1
            return (now - timedelta(minutes=n)).isoformat()
        if "hour" in time_str:
            n = int(time_str.split()[0]) if time_str[0].isdigit() else 1
            return (now - timedelta(hours=n)).isoformat()
        if "day" in time_str:
            n = int(time_str.split()[0]) if time_str[0].isdigit() else 1
            return (now - timedelta(days=n)).isoformat()
        if "week" in time_str:
            n = int(time_str.split()[0]) if time_str[0].isdigit() else 1
            return (now - timedelta(weeks=n)).isoformat()
    except (ValueError, IndexError):
        pass
    return now.isoformat()


def _fetch_job_description(job_url: str) -> str:
    """Fetch full job description from the job detail page."""
    try:
        resp = requests.get(job_url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        desc_div = soup.find("div", class_="description__text")
        if desc_div:
            return desc_div.get_text(separator="\n", strip=True)[:4000]
    except Exception as e:
        logger.warning(f"Could not fetch LinkedIn job description: {e}")
    return ""


def search(keywords: list[str], location: str = "Ireland", max_results: int = 20) -> list[Job]:
    jobs = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    for keyword in keywords:
        logger.info(f"LinkedIn: searching '{keyword}' in {location}")
        start = 0
        while len(jobs) < max_results:
            params = {
                "keywords": keyword,
                "location": location,
                "f_TPR": "r86400",  # Last 24 hours
                "position": start,
                "pageNum": 0,
                "count": 10,
            }
            try:
                resp = requests.get(SEARCH_URL, params=params, headers=HEADERS, timeout=20)
                if resp.status_code != 200:
                    logger.warning(f"LinkedIn returned {resp.status_code}")
                    break
                soup = BeautifulSoup(resp.text, "html.parser")
                cards = soup.find_all("div", class_="job-search-card")
                if not cards:
                    break

                for card in cards:
                    try:
                        title_el = card.find("h3", class_="base-search-card__title")
                        company_el = card.find("h4", class_="base-search-card__subtitle")
                        location_el = card.find("span", class_="job-search-card__location")
                        time_el = card.find("time")
                        link_el = card.find("a", class_="base-card__full-link")

                        title = title_el.get_text(strip=True) if title_el else "Unknown"
                        company = company_el.get_text(strip=True) if company_el else "Unknown"
                        loc = location_el.get_text(strip=True) if location_el else location
                        posted_str = time_el.get("datetime", "") if time_el else ""
                        url = link_el["href"].split("?")[0] if link_el else ""

                        if not url:
                            continue

                        # Parse posted time
                        if posted_str:
                            try:
                                posted_at = datetime.fromisoformat(posted_str.replace("Z", "+00:00")).isoformat()
                            except ValueError:
                                posted_at = _parse_posted_time(
                                    time_el.get_text(strip=True) if time_el else "1 day"
                                )
                        else:
                            posted_at = _parse_posted_time(
                                time_el.get_text(strip=True) if time_el else "1 day"
                            )

                        job_id = _make_job_id(url)
                        description = _fetch_job_description(url)
                        time.sleep(1)  # Be respectful of rate limits

                        jobs.append(Job(
                            id=job_id,
                            platform="linkedin",
                            title=title,
                            company=company,
                            location=loc,
                            url=url,
                            description=description,
                            posted_at=posted_at,
                        ))
                    except Exception as e:
                        logger.warning(f"LinkedIn: error parsing card: {e}")

                start += 10
                time.sleep(2)

            except Exception as e:
                logger.error(f"LinkedIn search error: {e}")
                break

        time.sleep(3)

    seen = set()
    unique = []
    for job in jobs:
        if job.id not in seen:
            seen.add(job.id)
            unique.append(job)
    return unique
