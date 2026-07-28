import sqlite3
import os
from datetime import datetime
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(__file__), "jobs.db")


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                platform TEXT NOT NULL,
                title TEXT,
                company TEXT,
                location TEXT,
                url TEXT,
                description TEXT,
                posted_at TEXT,
                discovered_at TEXT DEFAULT CURRENT_TIMESTAMP,
                emailed INTEGER DEFAULT 0,
                applied INTEGER DEFAULT 0,
                apply_status TEXT,
                tailored_resume_path TEXT
            )
        """)


def job_exists(job_id: str) -> bool:
    with get_conn() as conn:
        row = conn.execute("SELECT id FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return row is not None


def save_job(job: dict):
    with get_conn() as conn:
        conn.execute("""
            INSERT OR IGNORE INTO jobs
                (id, platform, title, company, location, url, description, posted_at)
            VALUES (:id, :platform, :title, :company, :location, :url, :description, :posted_at)
        """, job)


def mark_emailed(job_ids: list[str]):
    with get_conn() as conn:
        conn.executemany(
            "UPDATE jobs SET emailed = 1 WHERE id = ?",
            [(jid,) for jid in job_ids]
        )


def mark_applied(job_id: str, status: str, tailored_resume_path: str = None):
    with get_conn() as conn:
        conn.execute(
            "UPDATE jobs SET applied = 1, apply_status = ?, tailored_resume_path = ? WHERE id = ?",
            (status, tailored_resume_path, job_id)
        )


def get_unemailed_jobs() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE emailed = 0 ORDER BY posted_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]
