import datetime
import os

import aiosqlite

DB_PATH = os.environ.get(
    "PATCHPILOT_DB_PATH",
    os.path.join(os.path.dirname(__file__), "..", "patchpilot.db"),
)


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS org_jobs (
                id TEXT PRIMARY KEY,
                org_name TEXT,
                status TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS findings (
                id              TEXT PRIMARY KEY,
                job_id          TEXT NOT NULL,
                rule_id         TEXT,
                severity        TEXT,
                category        TEXT,
                file_path       TEXT,
                line_number     INTEGER,
                cwe             TEXT,
                scanner         TEXT,
                message         TEXT,
                package_name    TEXT,
                package_version TEXT,
                ml_score        REAL,
                false_positive  INTEGER DEFAULT NULL,
                labeled_at      TEXT DEFAULT NULL,
                version         INTEGER DEFAULT 1,
                created_at      TEXT DEFAULT (datetime('now'))
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                job_id       TEXT PRIMARY KEY,
                project_name TEXT,
                scan_method  TEXT,
                created_at   TEXT DEFAULT (datetime('now'))
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS verify_outcomes (
                id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                passed INTEGER NOT NULL,
                new_issues_introduced INTEGER DEFAULT 0,
                verified_at TEXT DEFAULT (datetime('now'))
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS contributor_stats (
                github_username TEXT PRIMARY KEY,
                findings_closed INTEGER DEFAULT 0,
                fixes_passed INTEGER DEFAULT 0,
                prs_merged INTEGER DEFAULT 0,
                last_updated TEXT DEFAULT (datetime('now'))
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS dependency_links (
                id TEXT PRIMARY KEY,
                org_job_id TEXT NOT NULL,
                project_name TEXT NOT NULL,
                package_name TEXT NOT NULL,
                package_version TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS fixes (
                id              TEXT PRIMARY KEY,
                job_id          TEXT NOT NULL,
                finding_id      TEXT NOT NULL,
                diff_line_count INTEGER,
                diff_file_count INTEGER,
                fix_type        TEXT,   -- 'insert' | 'delete' | 'mixed' | 'none'
                created_at      TEXT DEFAULT (datetime('now'))
            )
        """)

        db.row_factory = aiosqlite.Row
        cursor = await db.execute("PRAGMA table_info(findings)")
        columns = [row["name"] for row in await cursor.fetchall()]

        if "package_name" not in columns:
            await db.execute("ALTER TABLE findings ADD COLUMN package_name TEXT")
            await db.execute("ALTER TABLE findings ADD COLUMN package_version TEXT")

        if "ml_score" not in columns:
            await db.execute("ALTER TABLE findings ADD COLUMN ml_score REAL")

        if "false_positive" not in columns:
            await db.execute(
                "ALTER TABLE findings ADD COLUMN false_positive INTEGER DEFAULT NULL"
            )

        if "labeled_at" not in columns:
            await db.execute(
                "ALTER TABLE findings ADD COLUMN labeled_at TEXT DEFAULT NULL"
            )

        if "version" not in columns:
            await db.execute(
                "ALTER TABLE findings ADD COLUMN version INTEGER DEFAULT 1"
            )

        cursor = await db.execute("PRAGMA table_info(jobs)")
        job_columns = [row["name"] for row in await cursor.fetchall()]

        if "org_job_id" not in job_columns:
            await db.execute("ALTER TABLE jobs ADD COLUMN org_job_id TEXT")
        if "status" not in job_columns:
            await db.execute(
                "ALTER TABLE jobs ADD COLUMN status TEXT DEFAULT 'completed'"
            )
        if "raw_finding_count" not in job_columns:
            await db.execute("ALTER TABLE jobs ADD COLUMN raw_finding_count INTEGER")
        if "finding_count" not in job_columns:
            await db.execute("ALTER TABLE jobs ADD COLUMN finding_count INTEGER")

        await db.commit()


async def get_db():
    return await aiosqlite.connect(DB_PATH)


async def get_trend_data(limit: int = 6):
    """Fetches the finding counts for the last N scans for the dashboard."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT 
                j.created_at, 
                COUNT(f.id) as findings_count
            FROM jobs j
            LEFT JOIN findings f ON j.job_id = f.job_id
            GROUP BY j.job_id
            ORDER BY j.created_at DESC
            LIMIT ?
        """,
            (limit,),
        )

        rows = await cursor.fetchall()
        rows = list(reversed(rows))

        formatted_data = []
        for row in rows:
            dt_obj = datetime.datetime.strptime(row["created_at"], "%Y-%m-%d %H:%M:%S")
            formatted_data.append(
                {"date": dt_obj.strftime("%b %d"), "findings": row["findings_count"]}
            )

        return formatted_data


async def get_cwe_distribution():
    """Fetches the vulnerability distribution for the most recent scan."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            "SELECT job_id FROM jobs ORDER BY created_at DESC LIMIT 1"
        )
        latest_job = await cursor.fetchone()

        if not latest_job:
            return []

        job_id = latest_job["job_id"]
        cursor = await db.execute(
            """
            SELECT category as name, COUNT(id) as value
            FROM findings
            WHERE job_id = ?
            GROUP BY category
            ORDER BY value DESC
        """,
            (job_id,),
        )

        rows = await cursor.fetchall()
        return [{"name": row["name"], "value": row["value"]} for row in rows]


async def get_dependency_diff():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT job_id, project_name FROM jobs ORDER BY created_at DESC LIMIT 1"
        )
        latest_job = await cursor.fetchone()

        if not latest_job:
            return {"introduced": [], "resolved": [], "persistent": []}

        target_project = latest_job["project_name"]

        cursor = await db.execute(
            "SELECT job_id FROM jobs WHERE project_name = ? ORDER BY created_at DESC LIMIT 2",
            (target_project,),
        )
        jobs = await cursor.fetchall()

        if len(jobs) < 2:
            return {"introduced": [], "resolved": [], "persistent": []}

        new_job_id = jobs[0]["job_id"]
        old_job_id = jobs[1]["job_id"]

        query = """
            SELECT id, rule_id, severity, message, package_name, package_version
            FROM findings
            WHERE job_id = ? AND category = 'dependency'
        """

        cur_new = await db.execute(query, (new_job_id,))
        new_findings = await cur_new.fetchall()

        cur_old = await db.execute(query, (old_job_id,))
        old_findings = await cur_old.fetchall()

        def make_key(f):
            return (f["rule_id"], f["package_name"])

        old_dict = {make_key(f): dict(f) for f in old_findings}
        new_dict = {make_key(f): dict(f) for f in new_findings}

        introduced = []
        resolved = []
        persistent = []

        for key, new_f in new_dict.items():
            if key in old_dict:
                persistent.append(new_f)
            else:
                introduced.append(new_f)

        for key, old_f in old_dict.items():
            if key not in new_dict:
                resolved.append(old_f)

        return {
            "introduced": introduced,
            "resolved": resolved,
            "persistent": persistent,
        }


async def get_leaderboard_stats():
    """Fetches all contributors sorted by their weighted score."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT 
                github_username,
                findings_closed,
                fixes_passed,
                prs_merged,
                last_updated,
                (fixes_passed * 3) + (prs_merged * 2) + (findings_closed * 1) as total_score
            FROM contributor_stats
            ORDER BY total_score DESC
        """)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def upsert_contributor_stat(
    username: str, findings: int = 0, fixes: int = 0, prs: int = 0
):
    """Increments a contributor's stats. Creates the row if they don't exist."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO contributor_stats 
                (github_username, findings_closed, fixes_passed, prs_merged, last_updated)
            VALUES 
                (?, ?, ?, ?, datetime('now'))
            ON CONFLICT(github_username) DO UPDATE SET
                findings_closed = findings_closed + excluded.findings_closed,
                fixes_passed = fixes_passed + excluded.fixes_passed,
                prs_merged = prs_merged + excluded.prs_merged,
                last_updated = datetime('now')
        """,
            (username, findings, fixes, prs),
        )
        await db.commit()
