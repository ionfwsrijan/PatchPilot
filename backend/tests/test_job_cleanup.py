import os
from datetime import datetime, timedelta, timezone

import aiosqlite
import pytest

from app import cleanup, db
from app.cleanup import cleanup_expired_jobs, job_ttl_hours

NOW = datetime(2026, 10, 23, 12, 0, 0, tzinfo=timezone.utc)
OLD = (NOW - timedelta(hours=30)).strftime("%Y-%m-%d %H:%M:%S")
RECENT = (NOW - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")


@pytest.fixture
async def env(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    await db.init_db()
    work_root = tmp_path / "work"
    work_root.mkdir()
    return work_root


async def add_job(work_root, job_id, created_at, org_job_id=None):
    (work_root / job_id / "repo").mkdir(parents=True)
    (work_root / job_id / "repo" / "main.py").write_text("print('hi')")
    async with aiosqlite.connect(db.DB_PATH) as conn:
        await conn.execute(
            "INSERT INTO jobs (job_id, project_name, scan_method, org_job_id, created_at)"
            " VALUES (?, 'proj', 'zip', ?, ?)",
            (job_id, org_job_id, created_at),
        )
        await conn.execute(
            "INSERT INTO findings (id, job_id, rule_id) VALUES (?, ?, 'r1')",
            (f"f-{job_id}", job_id),
        )
        await conn.execute(
            "INSERT INTO verify_outcomes (id, job_id, passed) VALUES (?, ?, 1)",
            (f"v-{job_id}", job_id),
        )
        await conn.execute(
            "INSERT INTO fixes (id, job_id, finding_id) VALUES (?, ?, ?)",
            (f"x-{job_id}", job_id, f"f-{job_id}"),
        )
        await conn.commit()


async def count(table, column, value):
    async with aiosqlite.connect(db.DB_PATH) as conn:
        cursor = await conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE {column} = ?",  # noqa: S608 - fixed test tables
            (value,),
        )
        return (await cursor.fetchone())[0]


def make_old(path, hours=30):
    stamp = (NOW - timedelta(hours=hours)).timestamp()
    os.utime(path, (stamp, stamp))


@pytest.mark.anyio
async def test_expired_job_is_removed_with_all_rows(env):
    await add_job(env, "oldjob01", OLD)

    removed = await cleanup_expired_jobs(env, 24, now=NOW)

    assert removed == 1
    assert not (env / "oldjob01").exists()
    for table in ("jobs", "findings", "verify_outcomes", "fixes"):
        assert await count(table, "job_id", "oldjob01") == 0


@pytest.mark.anyio
async def test_recent_job_is_preserved(env):
    await add_job(env, "newjob01", RECENT)

    removed = await cleanup_expired_jobs(env, 24, now=NOW)

    assert removed == 0
    assert (env / "newjob01" / "repo" / "main.py").exists()
    assert await count("jobs", "job_id", "newjob01") == 1
    assert await count("findings", "job_id", "newjob01") == 1


@pytest.mark.anyio
async def test_running_scan_is_never_removed(env):
    await add_job(env, "running1", OLD)

    removed = await cleanup_expired_jobs(env, 24, active_job_ids={"running1"}, now=NOW)

    assert removed == 0
    assert (env / "running1").exists()
    assert await count("jobs", "job_id", "running1") == 1


@pytest.mark.anyio
async def test_jobs_of_running_org_batch_are_skipped(env):
    async with aiosqlite.connect(db.DB_PATH) as conn:
        await conn.execute(
            "INSERT INTO org_jobs (id, org_name, status, created_at) VALUES ('org-1', 'acme', 'scanning', ?)",
            (OLD,),
        )
        await conn.commit()
    await add_job(env, "orgjob01", OLD, org_job_id="org-1")

    removed = await cleanup_expired_jobs(env, 24, active_org_job_ids={"org-1"}, now=NOW)

    assert removed == 0
    assert await count("jobs", "job_id", "orgjob01") == 1
    assert await count("org_jobs", "id", "org-1") == 1


@pytest.mark.anyio
async def test_finished_org_job_is_removed_with_dependency_links(env):
    async with aiosqlite.connect(db.DB_PATH) as conn:
        await conn.execute(
            "INSERT INTO org_jobs (id, org_name, status, created_at) VALUES ('org-1', 'acme', 'completed', ?)",
            (OLD,),
        )
        await conn.execute(
            "INSERT INTO dependency_links (id, org_job_id, project_name, package_name) VALUES ('d1', 'org-1', 'proj', 'lodash')"
        )
        await conn.commit()
    await add_job(env, "orgjob01", OLD, org_job_id="org-1")

    removed = await cleanup_expired_jobs(env, 24, now=NOW)

    assert removed == 1
    assert await count("org_jobs", "id", "org-1") == 0
    assert await count("dependency_links", "org_job_id", "org-1") == 0


@pytest.mark.anyio
async def test_org_job_with_recent_children_is_kept(env):
    async with aiosqlite.connect(db.DB_PATH) as conn:
        await conn.execute(
            "INSERT INTO org_jobs (id, org_name, status, created_at) VALUES ('org-1', 'acme', 'completed', ?)",
            (OLD,),
        )
        await conn.commit()
    await add_job(env, "orgjob01", RECENT, org_job_id="org-1")

    await cleanup_expired_jobs(env, 24, now=NOW)

    assert await count("org_jobs", "id", "org-1") == 1


@pytest.mark.anyio
async def test_orphaned_workspace_folders(env):
    old_orphan = env / "abc12_xy"
    recent_orphan = env / "zz99_new"
    unrelated = env / "my-notes"
    for folder in (old_orphan, recent_orphan, unrelated):
        folder.mkdir()
    make_old(old_orphan)
    make_old(unrelated)

    await cleanup_expired_jobs(env, 24, now=NOW)

    assert not old_orphan.exists()
    assert recent_orphan.exists()
    assert unrelated.exists()


@pytest.mark.anyio
async def test_old_workspace_of_running_scan_without_row_is_kept(env):
    folder = env / "upload01"
    folder.mkdir()
    make_old(folder)

    await cleanup_expired_jobs(env, 24, active_job_ids={"upload01"}, now=NOW)

    assert folder.exists()


@pytest.mark.anyio
async def test_zero_ttl_disables_cleanup(env):
    await add_job(env, "oldjob01", OLD)

    removed = await cleanup_expired_jobs(env, 0, now=NOW)

    assert removed == 0
    assert (env / "oldjob01").exists()


@pytest.mark.anyio
async def test_cleanup_logs_counts_at_info(env, caplog):
    await add_job(env, "oldjob01", OLD)

    with caplog.at_level("INFO", logger="app.cleanup"):
        await cleanup_expired_jobs(env, 24, now=NOW)

    assert "removed 1 jobs" in caplog.text


@pytest.mark.anyio
async def test_cleanup_is_safe_to_run_twice(env):
    await add_job(env, "oldjob01", OLD)

    assert await cleanup_expired_jobs(env, 24, now=NOW) == 1
    assert await cleanup_expired_jobs(env, 24, now=NOW) == 0


@pytest.mark.anyio
async def test_delete_job_also_removes_fixes(env):
    await add_job(env, "oldjob01", RECENT)

    async with aiosqlite.connect(db.DB_PATH) as conn:
        await db.delete_job(conn, "oldjob01")

    assert await count("fixes", "job_id", "oldjob01") == 0


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(None, 24.0), ("", 24.0), ("48", 48.0), ("0.5", 0.5), ("0", 0.0), ("abc", 24.0)],
)
def test_job_ttl_hours_from_env(monkeypatch, raw, expected):
    if raw is None:
        monkeypatch.delenv("JOB_TTL_HOURS", raising=False)
    else:
        monkeypatch.setenv("JOB_TTL_HOURS", raw)
    assert job_ttl_hours() == expected


def test_cleanup_interval_is_one_hour():
    assert cleanup.CLEANUP_INTERVAL_SECONDS == 3600
