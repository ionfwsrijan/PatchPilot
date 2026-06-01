import aiosqlite
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "patchpilot.db")

async def get_db():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        yield db

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS findings (
                id          TEXT PRIMARY KEY,
                job_id      TEXT NOT NULL,
                rule_id     TEXT,
                severity    TEXT,
                category    TEXT,
                file_path   TEXT,
                line_number INTEGER,
                cwe         TEXT,
                scanner     TEXT,   -- 'semgrep' | 'osv' | 'gitleaks'
                message     TEXT,
                created_at  TEXT DEFAULT (datetime('now'))
            );
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS jobs (
                job_id      TEXT PRIMARY KEY,
                project_name TEXT,
                scan_method TEXT,   -- 'zip' | 'url'
                created_at  TEXT DEFAULT (datetime('now'))
            );
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS verify_outcomes (
                id                      TEXT PRIMARY KEY,
                job_id                  TEXT NOT NULL,
                passed                  INTEGER NOT NULL,  -- 1 = passed, 0 = failed
                new_issues_introduced   INTEGER DEFAULT 0,
                verified_at             TEXT DEFAULT (datetime('now'))
            );
        ''')
        await db.commit()