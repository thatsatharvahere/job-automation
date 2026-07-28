# job-automation

Scrapes LinkedIn, Indeed, Jobs.ie, and GradIreland for new job postings, tailors your resume for each match with an LLM, emails you a digest, optionally auto-applies via LinkedIn/Indeed Easy Apply, and logs everything to a spreadsheet tracker.

## Prerequisites

- Python 3.11+ (tested on 3.14)
- Google Chrome installed (required for `selenium` / `undetected-chromedriver`, only if `auto_apply: true`)
- A Gmail account with an [App Password](https://myaccount.google.com/apppasswords) (2FA must be enabled first)
- A free [Groq API key](https://console.groq.com/keys) for resume tailoring

## Setup

1. **Clone the repo**
   ```bash
   git clone https://github.com/thatsatharvahere/job-automation.git
   cd job-automation
   ```

2. **Create a virtual environment and install dependencies**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Create your config file from the template**
   ```bash
   cp config.example.yaml config.yaml
   ```
   Then edit `config.yaml` and fill in:
   - `search.keywords` / `search.location` — what jobs to look for
   - `email.sender_address` / `email.sender_app_password` / `email.recipient` — for the Gmail digest
   - `resume.path` — full path to your base resume (`.docx`)
   - `groq.api_key` — from console.groq.com
   - `linkedin.email` / `linkedin.password` and `indeed.email` / `indeed.password` — only needed if auto-apply is enabled
   - `personal_info` — used to fill application forms

   `config.yaml` is gitignored — never commit it, it holds real credentials.

4. **Fix Python's SSL certificates (macOS only, one-time)**

   If auto-apply fails with `CERTIFICATE_VERIFY_FAILED`, run the certificate installer that ships with the python.org installer:
   ```bash
   "/Applications/Python 3.14/Install Certificates.command"
   ```
   (adjust the version number to match your installed Python)

5. **Do a dry run first**

   In `config.yaml`, set:
   ```yaml
   settings:
     dry_run: true
     auto_apply: false
   ```
   Then run manually:
   ```bash
   python3 main.py
   ```
   Check the email digest and `Job_Applications_Tracker.xlsx` before enabling auto-apply.

6. **Enable auto-apply (optional)**

   Once you've reviewed a few dry runs, set `auto_apply: true` and `dry_run: false` in `config.yaml`.

## Running automatically on a schedule (macOS `launchd`)

1. Create `~/Library/LaunchAgents/com.<you>.jobautomation.plist` pointing `ProgramArguments` at your Python interpreter and `main.py`, with `WorkingDirectory` set to this repo's path. Set `StartCalendarInterval` entries for whatever times you want it to run (e.g. 7am/1pm/7pm).

2. Load it:
   ```bash
   launchctl load ~/Library/LaunchAgents/com.<you>.jobautomation.plist
   ```

3. Check status any time:
   ```bash
   launchctl list | grep jobautomation
   ```

4. Logs land in `logs/` — one timestamped file per run, plus `logs/launchctl.log` and `logs/launchctl_error.log` for launchd's own stdout/stderr.

This plist survives reboots and re-registers automatically at login — no extra step needed after a restart.

## Project structure

| File | Purpose |
|---|---|
| `main.py` | Orchestrates a full run: search → tailor → email → apply → track |
| `scrapers/` | Per-site job scrapers (LinkedIn, Indeed, Jobs.ie, GradIreland) |
| `resume_tailor.py` | Rewrites resume bullets per job using Groq |
| `auto_apply.py` | Selenium-based Easy Apply for LinkedIn/Indeed |
| `email_notifier.py` | Sends the digest and application-confirmation emails |
| `spreadsheet_tracker.py` | Appends results to `Job_Applications_Tracker.xlsx` |
| `database.py` | Tracks previously-seen jobs to avoid duplicates |

## Notes

- `config.yaml`, `logs/`, `jobs.db`, `tailored_resumes/`, and `Job_Applications_Tracker.xlsx` are all gitignored — they contain credentials or personal data and are regenerated locally.
- `min_hours_before_apply` in `config.yaml` delays applying to a posting until it's been up for at least that long, to avoid being first-to-apply bot-detection patterns.
