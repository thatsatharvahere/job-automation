import logging
import os
import smtplib
from datetime import datetime
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

PLATFORM_COLORS = {
    "linkedin": "#0077B5",
    "indeed": "#003A9B",
    "jobs.ie": "#E84545",
    "gradireland": "#2E7D32",
}

PLATFORM_LABELS = {
    "linkedin": "LinkedIn",
    "indeed": "Indeed",
    "jobs.ie": "Jobs.ie",
    "gradireland": "GradIreland",
}


def _platform_badge(platform: str) -> str:
    color = PLATFORM_COLORS.get(platform, "#555")
    label = PLATFORM_LABELS.get(platform, platform.title())
    return (
        f'<span style="background:{color};color:white;padding:2px 8px;'
        f'border-radius:12px;font-size:11px;font-weight:bold;">{label}</span>'
    )


def _format_posted_time(posted_at: str) -> str:
    try:
        from datetime import timezone, timedelta
        dt = datetime.fromisoformat(posted_at)
        if dt.tzinfo is None:
            from datetime import timezone
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        diff = now - dt
        hours = int(diff.total_seconds() / 3600)
        if hours < 1:
            return "Just posted"
        if hours == 1:
            return "1 hour ago"
        if hours < 24:
            return f"{hours} hours ago"
        return "1 day ago"
    except Exception:
        return "Recently posted"


def _build_html(jobs: list[dict]) -> str:
    by_platform: dict[str, list] = {}
    for job in jobs:
        by_platform.setdefault(job["platform"], []).append(job)

    job_cards = ""
    for platform, platform_jobs in by_platform.items():
        job_cards += f"""
        <h2 style="color:#333;border-bottom:2px solid {PLATFORM_COLORS.get(platform,'#ccc')};
                   padding-bottom:6px;margin-top:32px;">
            {PLATFORM_LABELS.get(platform, platform.title())} — {len(platform_jobs)} new job(s)
        </h2>"""

        for job in platform_jobs:
            desc_preview = (job.get("description") or "")[:300].replace("\n", " ")
            if len(job.get("description", "")) > 300:
                desc_preview += "..."

            job_cards += f"""
        <div style="border:1px solid #e0e0e0;border-radius:8px;padding:16px;
                    margin:12px 0;background:#fafafa;">
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
                {_platform_badge(platform)}
                <span style="color:#888;font-size:12px;">{_format_posted_time(job.get('posted_at',''))}</span>
            </div>
            <h3 style="margin:0 0 4px 0;color:#1a1a1a;font-size:16px;">{job['title']}</h3>
            <p style="margin:0 0 8px 0;color:#555;font-size:14px;">
                <strong>{job['company']}</strong> &bull; {job['location']}
            </p>
            <p style="margin:0 0 12px 0;color:#666;font-size:13px;line-height:1.5;">
                {desc_preview}
            </p>
            <a href="{job['url']}" style="background:#0066cc;color:white;padding:8px 16px;
               border-radius:4px;text-decoration:none;font-size:13px;font-weight:bold;">
                View &amp; Apply →
            </a>
        </div>"""

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
             max-width:680px;margin:0 auto;padding:20px;color:#333;">
    <div style="background:linear-gradient(135deg,#1a237e,#283593);
                color:white;padding:24px;border-radius:12px;margin-bottom:24px;">
        <h1 style="margin:0;font-size:22px;">Job Automation Report</h1>
        <p style="margin:8px 0 0 0;opacity:0.9;font-size:14px;">
            {len(jobs)} new job(s) found in the last 24 hours &bull;
            {datetime.now().strftime('%A, %d %B %Y at %H:%M')}
        </p>
    </div>

    {job_cards}

    <div style="margin-top:32px;padding:16px;background:#f5f5f5;border-radius:8px;
                font-size:12px;color:#888;text-align:center;">
        Tailored resumes are attached for each job where AI tailoring was applied.<br>
        This email was generated automatically by your job automation system.
    </div>
</body>
</html>"""


def send_job_digest(
    jobs: list[dict],
    tailored_resumes: dict[str, str],  # job_id -> resume path
    sender_address: str,
    sender_app_password: str,
    recipient: str,
    dry_run: bool = False,
) -> bool:
    """
    Send HTML email with all new jobs and attach tailored resumes.
    Returns True on success.
    """
    if not jobs:
        logger.info("No new jobs to email")
        return True

    subject = f"[Job Alert] {len(jobs)} new job(s) found — {datetime.now().strftime('%d %b %Y')}"

    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = sender_address
    msg["To"] = recipient

    html_body = _build_html(jobs)
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    # Attach unique tailored resumes
    attached_paths = set()
    for job in jobs:
        resume_path = tailored_resumes.get(job["id"])
        if resume_path and os.path.exists(resume_path) and resume_path not in attached_paths:
            attached_paths.add(resume_path)
            filename = os.path.basename(resume_path)
            with open(resume_path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
            msg.attach(part)

    if dry_run:
        logger.info(f"[DRY RUN] Would send email to {recipient} with {len(jobs)} jobs")
        logger.info(f"[DRY RUN] Subject: {subject}")
        return True

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(sender_address, sender_app_password)
            smtp.send_message(msg)
        logger.info(f"Email sent to {recipient} with {len(jobs)} jobs ({len(attached_paths)} resumes attached)")
        return True
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        return False


def _build_confirmation_html(jobs: list[dict], statuses: dict[str, str]) -> str:
    applied = [j for j in jobs if statuses.get(j["id"]) == "applied"]
    skipped = [j for j in jobs if statuses.get(j["id"], "").startswith("skipped")]
    failed  = [j for j in jobs if statuses.get(j["id"], "").startswith("failed")]

    def job_row(job, status_label, bg):
        return f"""
        <tr style="background:{bg};">
            <td style="padding:8px;border-bottom:1px solid #eee;">{job['title']}</td>
            <td style="padding:8px;border-bottom:1px solid #eee;">{job['company']}</td>
            <td style="padding:8px;border-bottom:1px solid #eee;">{PLATFORM_LABELS.get(job['platform'], job['platform'])}</td>
            <td style="padding:8px;border-bottom:1px solid #eee;font-weight:bold;">{status_label}</td>
            <td style="padding:8px;border-bottom:1px solid #eee;">
                <a href="{job['url']}" style="color:#0066cc;">View Job</a>
            </td>
        </tr>"""

    rows = ""
    for job in applied:
        rows += job_row(job, "Applied", "#E8F5E9")
    for job in skipped:
        label = "No Easy Apply — Manual Required"
        rows += job_row(job, label, "#FFFDE7")
    for job in failed:
        rows += job_row(job, "Failed", "#FFEBEE")

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
             max-width:720px;margin:0 auto;padding:20px;color:#333;">

    <div style="background:linear-gradient(135deg,#1B5E20,#2E7D32);
                color:white;padding:24px;border-radius:12px;margin-bottom:24px;">
        <h1 style="margin:0;font-size:22px;">Application Confirmation</h1>
        <p style="margin:8px 0 0 0;opacity:0.9;font-size:14px;">
            {datetime.now().strftime('%A, %d %B %Y at %H:%M')}
        </p>
    </div>

    <div style="display:flex;gap:12px;margin-bottom:24px;">
        <div style="flex:1;background:#E8F5E9;border-radius:8px;padding:16px;text-align:center;">
            <div style="font-size:32px;font-weight:bold;color:#2E7D32;">{len(applied)}</div>
            <div style="color:#555;font-size:13px;">Applied</div>
        </div>
        <div style="flex:1;background:#FFFDE7;border-radius:8px;padding:16px;text-align:center;">
            <div style="font-size:32px;font-weight:bold;color:#F57F17;">{len(skipped)}</div>
            <div style="color:#555;font-size:13px;">Manual Apply Required</div>
        </div>
        <div style="flex:1;background:#FFEBEE;border-radius:8px;padding:16px;text-align:center;">
            <div style="font-size:32px;font-weight:bold;color:#C62828;">{len(failed)}</div>
            <div style="color:#555;font-size:13px;">Failed</div>
        </div>
    </div>

    <table style="width:100%;border-collapse:collapse;font-size:13px;">
        <thead>
            <tr style="background:#1A237E;color:white;">
                <th style="padding:10px;text-align:left;">Job Title</th>
                <th style="padding:10px;text-align:left;">Company</th>
                <th style="padding:10px;text-align:left;">Platform</th>
                <th style="padding:10px;text-align:left;">Status</th>
                <th style="padding:10px;text-align:left;">Link</th>
            </tr>
        </thead>
        <tbody>{rows}</tbody>
    </table>

    {"<p style='margin-top:20px;padding:12px;background:#FFF9C4;border-radius:8px;font-size:13px;'><strong>Manual apply required:</strong> " + str(len(skipped)) + " job(s) above don't have Easy Apply. Open the Job Applications Tracker for their links and apply manually.</p>" if skipped else ""}

    <div style="margin-top:24px;padding:16px;background:#f5f5f5;border-radius:8px;
                font-size:12px;color:#888;text-align:center;">
        The Job Applications Tracker spreadsheet has been updated with all entries above.
    </div>
</body>
</html>"""


def send_confirmation_email(
    jobs: list[dict],
    statuses: dict[str, str],
    tracker_path: str,
    sender_address: str,
    sender_app_password: str,
    recipient: str,
    dry_run: bool = False,
) -> bool:
    """Send confirmation email listing which jobs were applied to, with tracker attached."""
    applied_count = sum(1 for s in statuses.values() if s == "applied")
    subject = (
        f"[Applied] {applied_count} application(s) submitted — "
        f"{datetime.now().strftime('%d %b %Y %H:%M')}"
    )

    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = sender_address
    msg["To"] = recipient
    msg.attach(MIMEText(_build_confirmation_html(jobs, statuses), "html", "utf-8"))

    # Attach the updated tracker spreadsheet
    if tracker_path and os.path.exists(tracker_path):
        with open(tracker_path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            f'attachment; filename="{os.path.basename(tracker_path)}"'
        )
        msg.attach(part)

    if dry_run:
        logger.info(f"[DRY RUN] Would send confirmation email: {subject}")
        return True

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(sender_address, sender_app_password)
            smtp.send_message(msg)
        logger.info(f"Confirmation email sent: {applied_count} applications")
        return True
    except Exception as e:
        logger.error(f"Failed to send confirmation email: {e}")
        return False
