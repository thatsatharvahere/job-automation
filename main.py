#!/usr/bin/env python3
"""
Job Automation — Main Orchestrator

Runs every 6 hours via launchctl. Searches LinkedIn, Indeed, Jobs.ie,
and GradIreland for new jobs posted in the last 24 hours, tailors
your resume for each, emails a digest, and optionally auto-applies.
"""

import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import yaml

# Configure logging
log_dir = Path(__file__).parent / "logs"
log_dir.mkdir(exist_ok=True)
log_file = log_dir / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("main")

BASE_DIR = Path(__file__).parent


def load_config() -> dict:
    config_path = BASE_DIR / "config.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def run():
    logger.info("=" * 60)
    logger.info("Job Automation starting")
    logger.info("=" * 60)

    config = load_config()
    keywords = config["search"]["keywords"]
    location = config["search"]["location"]
    max_jobs = config["search"].get("max_jobs_per_run", 20)
    dry_run = config["settings"].get("dry_run", False)
    auto_apply = config["settings"].get("auto_apply", False)

    if dry_run:
        logger.info("DRY RUN mode — no emails or applications will be sent")

    # Initialize database
    from database import init_db, job_exists, save_job, mark_emailed, mark_applied, get_unemailed_jobs
    init_db()

    # --- STEP 1: Scrape all platforms ---
    all_new_jobs = []

    from scrapers import linkedin, indeed, jobsie, gradireland

    logger.info("Scraping LinkedIn...")
    try:
        lj = linkedin.search(keywords, location, max_jobs)
        logger.info(f"LinkedIn: {len(lj)} jobs found")
        all_new_jobs.extend(lj)
    except Exception as e:
        logger.error(f"LinkedIn scraper failed: {e}")

    logger.info("Scraping Indeed...")
    try:
        ij = indeed.search(keywords, location, max_jobs)
        logger.info(f"Indeed: {len(ij)} jobs found")
        all_new_jobs.extend(ij)
    except Exception as e:
        logger.error(f"Indeed scraper failed: {e}")

    logger.info("Scraping Jobs.ie...")
    try:
        jj = jobsie.search(keywords, location, max_jobs)
        logger.info(f"Jobs.ie: {len(jj)} jobs found")
        all_new_jobs.extend(jj)
    except Exception as e:
        logger.error(f"Jobs.ie scraper failed: {e}")

    logger.info("Scraping GradIreland...")
    try:
        gj = gradireland.search(keywords, location, max_jobs)
        logger.info(f"GradIreland: {len(gj)} jobs found")
        all_new_jobs.extend(gj)
    except Exception as e:
        logger.error(f"GradIreland scraper failed: {e}")

    # --- STEP 2: Filter out already-seen jobs ---
    new_jobs = []
    for job in all_new_jobs:
        if not job_exists(job.id):
            save_job(job.to_dict())
            new_jobs.append(job.to_dict())
        else:
            logger.debug(f"Skipping already-seen job: {job.id}")

    logger.info(f"Found {len(new_jobs)} new jobs (not previously seen)")

    if not new_jobs:
        logger.info("No new jobs — nothing to do")
        return

    # --- STEP 3: Tailor resumes ---
    from resume_tailor import tailor_resume
    tailored_resumes = {}  # job_id -> resume path

    groq_cfg = config.get("groq", {})
    api_key = groq_cfg.get("api_key", "")
    model = groq_cfg.get("model", "llama-3.1-8b-instant")
    resume_path = config["resume"]["path"]
    output_dir = config["resume"]["output_dir"]

    if not os.path.exists(resume_path):
        logger.error(f"Resume not found at: {resume_path}")
        logger.error("Update 'resume.path' in config.yaml")
        return

    for job in new_jobs:
        logger.info(f"Tailoring resume for: {job['title']} @ {job['company']}")
        try:
            tailored_path = tailor_resume(
                resume_path=resume_path,
                job_title=job["title"],
                company=job["company"],
                job_description=job.get("description", ""),
                output_dir=output_dir,
                api_key=api_key,
                model=model,
            )
            tailored_resumes[job["id"]] = tailored_path
        except Exception as e:
            logger.error(f"Resume tailoring failed for {job['id']}: {e}")
            tailored_resumes[job["id"]] = resume_path

    # --- STEP 4: Send email digest ---
    from email_notifier import send_job_digest
    email_cfg = config["email"]

    success = send_job_digest(
        jobs=new_jobs,
        tailored_resumes=tailored_resumes,
        sender_address=email_cfg["sender_address"],
        sender_app_password=email_cfg["sender_app_password"],
        recipient=email_cfg["recipient"],
        dry_run=dry_run,
    )

    if success:
        mark_emailed([job["id"] for job in new_jobs])

    # --- STEP 5: Auto-apply ---
    if auto_apply:
        logger.info("Auto-apply is ENABLED — attempting to apply to Easy Apply jobs")
        from auto_apply import apply_to_jobs

        statuses = apply_to_jobs(
            jobs=new_jobs,
            tailored_resumes=tailored_resumes,
            config=config,
            dry_run=dry_run,
        )

        for job in new_jobs:
            status = statuses.get(job["id"], "unknown")
            if status == "applied":
                mark_applied(job["id"], status, tailored_resumes.get(job["id"]))
            logger.info(f"  {job['title']} @ {job['company']}: {status}")

        applied_count = sum(1 for s in statuses.values() if s == "applied")
        logger.info(f"Auto-apply complete: {applied_count}/{len(new_jobs)} applications submitted")

        # --- STEP 6: Update spreadsheet tracker ---
        from spreadsheet_tracker import update_tracker
        tracker_path = update_tracker(new_jobs, statuses, tailored_resumes)
        logger.info(f"Tracker updated: {tracker_path}")

        # --- STEP 7: Send confirmation email with tracker attached ---
        from email_notifier import send_confirmation_email
        send_confirmation_email(
            jobs=new_jobs,
            statuses=statuses,
            tracker_path=tracker_path,
            sender_address=email_cfg["sender_address"],
            sender_app_password=email_cfg["sender_app_password"],
            recipient=email_cfg["recipient"],
            dry_run=dry_run,
        )
    else:
        logger.info("Auto-apply is DISABLED — review jobs via email and apply manually")

    logger.info("=" * 60)
    logger.info("Job Automation run complete")
    logger.info("=" * 60)


if __name__ == "__main__":
    run()
