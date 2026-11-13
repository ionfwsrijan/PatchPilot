"""Cleanup safety: last-activity expiry, jobs in use, atomic removal, shared workdir."""

import asyncio
import os
import shutil
import time
from pathlib import Path
from types import SimpleNamespace

import aiosqlite
import pytest
from fastapi.testclient import TestClient
from test_job_cleanup import NOW, OLD, RECENT, add_job, count, make_old

from app import cleanup, db, main
from app.cleanup import cleanup_expired_jobs, job_in_use
from app.models import VerifyResponse

TABLES = ("jobs", "findings", "verify_outcomes", "fixes")
# About 3.6 ms: anything not touched in the last few ms counts as idle.
TINY_TTL_HOURS = 1e-6


@pytest.fixture
async def env(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    await db.init_db()
    work_root = tmp_path / "work"
    work_root.mkdir()
    return work_root


@pytest.fixture
def api(tmp_path, monkeypatch):
    """A plain TestClient (no lifespan, so no background loops) on a temp db."""
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "api.db"))
    asyncio.run(db.init_db())
    work_root = tmp_path / "work"
    work_root.mkdir()
    monkeypatch.setattr(main, "WORK_ROOT", work_root)
    return SimpleNamespace(client=TestClient(main.app), work_root=work_root)


def run_cleanup_from_inside_a_request(work_root, ttl_hours=TINY_TTL_HOURS):
    """Run a cleanup pass while a request handler is mid-flight (in its thread)."""
    time.sleep(0.05)  # let the workspace look idle to the time based check
    return asyncio.run(cleanup_expired_jobs(work_root, ttl_hours))


def a_second_ago(path):
    stamp = time.time() - 1
    os.utime(path, (stamp, stamp))


# --- 1. which timestamp decides expiry ---------------------------------------


@pytest.mark.anyio
async def test_job_used_after_it_was_created_is_not_expired(env):
    await add_job(env, "usedjob1", OLD)
    # Fix / Verify / evidence pack refreshed the workspace 2 hours ago.
    stamp = NOW.timestamp() - 2 * 3600
    os.utime(env / "usedjob1", (stamp, stamp))

    removed = await cleanup_expired_jobs(env, 24, now=NOW)

    assert removed == 0
    assert (env / "usedjob1" / "repo" / "main.py").exists()
    for table in TABLES:
        assert await count(table, "job_id", "usedjob1") == 1


@pytest.mark.anyio
async def test_job_idle_since_creation_is_still_expired(env):
    await add_job(env, "idlejob1", OLD)

    assert await cleanup_expired_jobs(env, 24, now=NOW) == 1
    assert not (env / "idlejob1").exists()


@pytest.mark.anyio
async def test_job_in_use_refreshes_last_activity_on_enter_and_exit(env):
    await add_job(env, "usedjob1", OLD)
    make_old(env / "usedjob1")
    before = (env / "usedjob1").stat().st_mtime

    with job_in_use("usedjob1", env / "usedjob1"):
        assert (env / "usedjob1").stat().st_mtime > before
        a_second_ago(env / "usedjob1")
        during = (env / "usedjob1").stat().st_mtime

    assert (env / "usedjob1").stat().st_mtime > during


def test_job_in_use_on_a_missing_folder_does_not_raise(tmp_path):
    with job_in_use("gone0001", tmp_path / "gone0001"):
        pass


@pytest.mark.anyio
async def test_job_in_use_is_skipped_even_when_it_looks_idle(env):
    await add_job(env, "usedjob1", OLD)
    make_old(env / "usedjob1")

    with job_in_use("usedjob1", env / "usedjob1"):
        a_second_ago(env / "usedjob1")
        removed = await cleanup_expired_jobs(env, TINY_TTL_HOURS)
        assert removed == 0
        assert (env / "usedjob1").exists()
        assert await count("jobs", "job_id", "usedjob1") == 1

    # Once the request is done the protection is gone, the TTL counts from now.
    time.sleep(0.02)
    assert await cleanup_expired_jobs(env, TINY_TTL_HOURS) == 1
    assert not (env / "usedjob1").exists()


@pytest.mark.anyio
async def test_nested_use_of_one_job_is_counted(env):
    await add_job(env, "usedjob1", OLD)
    make_old(env / "usedjob1")

    with job_in_use("usedjob1", env / "usedjob1"):
        with job_in_use("usedjob1", env / "usedjob1"):
            pass
        time.sleep(0.02)
        # Still used by the outer request.
        assert await cleanup_expired_jobs(env, TINY_TTL_HOURS) == 0


def test_job_being_removed_cannot_be_entered(tmp_path):
    assert cleanup._claim_for_removal("gonejob1")
    try:
        with pytest.raises(cleanup.JobWorkspaceRemovedError):
            with job_in_use("gonejob1", tmp_path / "gonejob1"):
                pass
    finally:
        cleanup._release_claim("gonejob1")
    with job_in_use("gonejob1", tmp_path / "gonejob1"):
        pass


def test_fix_keeps_the_job_while_it_runs(api, monkeypatch):
    asyncio.run(add_job(api.work_root, "fixjob01", OLD))
    make_old(api.work_root / "fixjob01")
    seen = {}

    def fake_propose_fixes(repo_dir, finding_ids):
        seen["removed"] = run_cleanup_from_inside_a_request(api.work_root)
        return []

    monkeypatch.setattr(main, "propose_fixes", fake_propose_fixes)

    response = api.client.post("/fix", json={"job_id": "fixjob01", "finding_ids": []})

    assert response.status_code == 200
    assert seen["removed"] == 0
    assert (api.work_root / "fixjob01" / "repo").exists()
    # The TTL now counts from the end of the request.
    assert asyncio.run(cleanup_expired_jobs(api.work_root, 24)) == 0
    assert (api.work_root / "fixjob01").exists()


def test_verify_keeps_the_job_and_its_baseline_while_it_runs(api, monkeypatch):
    asyncio.run(add_job(api.work_root, "verjob01", OLD))
    asyncio.run(add_job(api.work_root, "basejob1", OLD))
    for name in ("verjob01", "basejob1"):
        make_old(api.work_root / name)
    seen = {}

    def fake_verify_repo(repo_dir):
        seen["removed"] = run_cleanup_from_inside_a_request(api.work_root)
        return VerifyResponse(ok=True, checks={})

    monkeypatch.setattr(main, "verify_repo", fake_verify_repo)
    monkeypatch.setattr(
        main, "_scan_repo_dir", lambda *args, **kwargs: ([], [], [], [], [])
    )

    response = api.client.post(
        "/verify", data={"job_id": "verjob01", "baseline_job_id": "basejob1"}
    )

    assert response.status_code == 200
    assert seen["removed"] == 0
    for name in ("verjob01", "basejob1"):
        assert (api.work_root / name / "repo").exists()
        assert asyncio.run(count("jobs", "job_id", name)) == 1


def test_verify_rejects_a_bad_baseline_id_before_doing_any_work(api, monkeypatch):
    asyncio.run(add_job(api.work_root, "verjob01", RECENT))
    called = []
    monkeypatch.setattr(main, "verify_repo", lambda repo_dir: called.append(1))

    response = api.client.post(
        "/verify", data={"job_id": "verjob01", "baseline_job_id": "../etc"}
    )

    assert response.status_code == 400
    assert called == []


def test_evidence_pack_keeps_the_job_while_it_is_built(api, monkeypatch):
    asyncio.run(add_job(api.work_root, "packjob1", OLD))
    make_old(api.work_root / "packjob1")
    seen = {}

    def fake_build_evidence_pack(*, repo_dir, out_dir, job_dir, **kwargs):
        seen["removed"] = run_cleanup_from_inside_a_request(api.work_root)
        pack = out_dir / "pack.zip"
        pack.write_bytes(b"PK")
        return pack

    monkeypatch.setattr(main, "build_evidence_pack", fake_build_evidence_pack)

    response = api.client.post("/evidence-pack", data={"job_id": "packjob1"})

    assert response.status_code == 200
    assert seen["removed"] == 0
    assert (api.work_root / "packjob1" / "repo").exists()


@pytest.mark.parametrize(
    ("path", "kwargs"),
    [
        ("/fix", {"json": {"job_id": "gonejob1", "finding_ids": []}}),
        ("/verify", {"data": {"job_id": "gonejob1"}}),
        ("/evidence-pack", {"data": {"job_id": "gonejob1"}}),
    ],
)
def test_requests_for_a_job_being_removed_get_a_404(api, path, kwargs):
    (api.work_root / "gonejob1" / "repo").mkdir(parents=True)
    assert cleanup._claim_for_removal("gonejob1")
    try:
        response = api.client.post(path, **kwargs)
    finally:
        cleanup._release_claim("gonejob1")

    assert response.status_code == 404
    assert response.json() == {"detail": "Unknown job_id"}


# --- 2. atomic removal, retry on failure --------------------------------------


def partly_removing_rmtree(path, *args, **kwargs):
    """An rmtree that deletes one file and then fails, like a busy/locked tree."""
    for victim in sorted(Path(path).rglob("*")):
        if victim.is_file():
            victim.unlink()
            break
    raise PermissionError(13, "Permission denied", str(path))


@pytest.mark.anyio
async def test_failed_workspace_removal_leaves_the_job_for_the_next_pass(
    env, monkeypatch, caplog
):
    await add_job(env, "stuckjob", OLD)
    (env / "stuckjob" / "repo" / "second.py").write_text("x = 1")
    with monkeypatch.context() as patched:
        patched.setattr(shutil, "rmtree", partly_removing_rmtree)
        with caplog.at_level("INFO", logger="app.cleanup"):
            removed = await cleanup_expired_jobs(env, 24, now=NOW)

    assert removed == 0
    # Nothing was deleted from the database, in any of the tables.
    for table in TABLES:
        assert await count(table, "job_id", "stuckjob") == 1
    assert (env / "stuckjob").exists()
    assert "Could not remove the workspace of expired job stuckjob" in caplog.text
    assert "1 jobs could not be removed" in caplog.text

    # Next pass: the leftovers are removed and then all rows go in one go.
    assert await cleanup_expired_jobs(env, 24, now=NOW) == 1
    assert not (env / "stuckjob").exists()
    for table in TABLES:
        assert await count(table, "job_id", "stuckjob") == 0


@pytest.mark.anyio
async def test_one_stuck_job_does_not_stop_the_others(env, monkeypatch):
    await add_job(env, "stuckjob", OLD)
    await add_job(env, "fine0001", OLD)
    real_rmtree = shutil.rmtree

    def fake(path, *args, **kwargs):
        if Path(path).name == "stuckjob":
            raise PermissionError(13, "Permission denied", str(path))
        return real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(shutil, "rmtree", fake)

    removed = await cleanup_expired_jobs(env, 24, now=NOW)

    assert removed == 1
    assert not (env / "fine0001").exists()
    assert await count("jobs", "job_id", "fine0001") == 0
    assert await count("jobs", "job_id", "stuckjob") == 1


async def block_fix_deletes_for(job_id):
    async with aiosqlite.connect(db.DB_PATH) as conn:
        await conn.execute(
            "CREATE TRIGGER block_fix_delete BEFORE DELETE ON fixes"
            f" WHEN OLD.job_id = '{job_id}'"
            " BEGIN SELECT RAISE(ABORT, 'disk is on fire'); END"
        )
        await conn.commit()


async def unblock_fix_deletes():
    async with aiosqlite.connect(db.DB_PATH) as conn:
        await conn.execute("DROP TRIGGER block_fix_delete")
        await conn.commit()


@pytest.mark.anyio
async def test_job_rows_are_deleted_all_or_nothing(env, caplog):
    await add_job(env, "badjob01", OLD)
    await add_job(env, "goodjob1", OLD)
    await block_fix_deletes_for("badjob01")

    with caplog.at_level("INFO", logger="app.cleanup"):
        removed = await cleanup_expired_jobs(env, 24, now=NOW)

    # The pass survived, the good job is gone, and the bad one keeps every row
    # (jobs and findings are not deleted just because fixes failed).
    assert removed == 1
    assert await count("jobs", "job_id", "goodjob1") == 0
    for table in TABLES:
        assert await count(table, "job_id", "badjob01") == 1
    assert "Could not delete the rows of expired job badjob01" in caplog.text

    # Retried on the next pass; the workspace is already gone, which is fine.
    await unblock_fix_deletes()
    assert await cleanup_expired_jobs(env, 24, now=NOW) == 1
    for table in TABLES:
        assert await count(table, "job_id", "badjob01") == 0


@pytest.mark.anyio
async def test_delete_job_rolls_back_when_one_delete_fails(env):
    await add_job(env, "badjob01", OLD)
    await block_fix_deletes_for("badjob01")

    async with aiosqlite.connect(db.DB_PATH) as conn:
        with pytest.raises(aiosqlite.Error):
            await db.delete_job(conn, "badjob01")
        # The same connection carries on and commits something else later on:
        # that must not make the earlier deletes stick.
        await conn.commit()

    for table in TABLES:
        assert await count(table, "job_id", "badjob01") == 1


@pytest.mark.anyio
async def test_org_job_removal_is_all_or_nothing(env):
    async with aiosqlite.connect(db.DB_PATH) as conn:
        await conn.execute(
            "INSERT INTO org_jobs (id, org_name, status, created_at) VALUES ('org-1', 'acme', 'completed', ?)",
            (OLD,),
        )
        await conn.execute(
            "INSERT INTO dependency_links (id, org_job_id, project_name, package_name) VALUES ('d1', 'org-1', 'proj', 'lodash')"
        )
        await conn.execute(
            "CREATE TRIGGER block_org_delete BEFORE DELETE ON org_jobs"
            " BEGIN SELECT RAISE(ABORT, 'nope'); END"
        )
        await conn.commit()

    await cleanup_expired_jobs(env, 24, now=NOW)

    assert await count("org_jobs", "id", "org-1") == 1
    assert await count("dependency_links", "org_job_id", "org-1") == 1


# --- 5. orphaned folders in a shared PATCHPILOT_WORKDIR ----------------------


@pytest.mark.anyio
async def test_shared_workdir_unrelated_folders_are_never_touched(env, tmp_path):
    outside = tmp_path / "outside"
    (outside / "repo").mkdir(parents=True)
    (outside / "repo" / "keep.txt").write_text("precious")

    # Looks like a job id (8 chars of [a-z0-9_]) but is somebody else's folder.
    lookalikes = [
        env / "projects",
        env / "archives",
        env / "backup_1",
        env / "data1234",
    ]
    for folder in lookalikes:
        (folder / "docs").mkdir(parents=True)
        (folder / "docs" / "file.txt").write_text("not patchpilot's")
    # Even a "repo" folder inside is not enough when the name is not a job id.
    other_repo = env / "my-project"
    (other_repo / "repo").mkdir(parents=True)
    # A plain file with a job id like name, and a symlink to a real workspace.
    stray_file = env / "file0001"
    stray_file.write_text("x")
    link = env / "link0001"
    link.symlink_to(outside, target_is_directory=True)
    # And the real orphan: generated name plus a repo folder.
    real_orphan = env / "orphan01"
    (real_orphan / "repo").mkdir(parents=True)

    for path in [*lookalikes, other_repo, stray_file, real_orphan, outside]:
        make_old(path)
    stamp = NOW.timestamp() - 30 * 3600
    os.utime(link, (stamp, stamp), follow_symlinks=False)

    await cleanup_expired_jobs(env, 24, now=NOW)

    for folder in lookalikes:
        assert (folder / "docs" / "file.txt").read_text() == "not patchpilot's"
    assert other_repo.exists()
    assert stray_file.read_text() == "x"
    assert link.is_symlink()
    assert (outside / "repo" / "keep.txt").read_text() == "precious"
    assert not real_orphan.exists()


@pytest.mark.anyio
async def test_orphan_of_a_job_in_use_is_kept(env):
    orphan = env / "orphan01"
    (orphan / "repo").mkdir(parents=True)
    make_old(orphan)

    with job_in_use("orphan01", orphan):
        a_second_ago(orphan)
        await cleanup_expired_jobs(env, TINY_TTL_HOURS)
        assert orphan.exists()


@pytest.mark.anyio
async def test_orphan_removal_failure_is_logged_and_does_not_crash(
    env, monkeypatch, caplog
):
    orphan = env / "orphan01"
    (orphan / "repo").mkdir(parents=True)
    make_old(orphan)
    monkeypatch.setattr(shutil, "rmtree", partly_removing_rmtree)

    with caplog.at_level("INFO", logger="app.cleanup"):
        await cleanup_expired_jobs(env, 24, now=NOW)

    assert "Could not remove orphaned workspace" in caplog.text
    assert orphan.exists()
