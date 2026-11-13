"""Automatic cleanup of expired scan workspaces and their database rows."""

from __future__ import annotations

import asyncio
import logging
import math
import os
import re
import shutil
import threading
from collections.abc import Collection, Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .db import delete_job, get_db
from .utils.fs import safe_job_dir

logger = logging.getLogger(__name__)

DEFAULT_JOB_TTL_HOURS = 24.0
CLEANUP_INTERVAL_SECONDS = 3600
# Wait this long after startup before the first pass, so a restart (or a test
# that starts the app) doesn't immediately delete things.
CLEANUP_STARTUP_DELAY_SECONDS = 60

# Job ids come from tempfile._get_candidate_names(): 8 chars of [a-z0-9_].
# Workspace folders without a jobs row are only removed when they match this
# AND contain a "repo" folder (every upload / URL / org scan creates one), so a
# PATCHPILOT_WORKDIR pointed at a shared folder can't lose unrelated dirs that
# just happen to have an 8 character name like "projects" or "archives".
_GENERATED_JOB_ID = re.compile(r"^[a-z0-9_]{8}$")
_WORKSPACE_MARKER = "repo"

# Which jobs are being used right now (Fix, Verify, evidence pack), so the
# cleanup doesn't remove a workspace out from under a request.
#
# NOTE: like ACTIVE_SCANS in main.py this is plain in-process memory. The
# "skip running scans / jobs in use" checks are only reliable when the API runs
# as a single process (one uvicorn worker, which is what the Dockerfile does).
# With several workers each one only knows about its own requests. The
# last-activity timestamp below (the workspace folder's mtime) is on disk, so
# it is shared, but it only covers the moment a request starts and ends.
_state_lock = threading.Lock()
_in_use: dict[str, int] = {}
_being_removed: set[str] = set()

# SQLite's datetime('now') format, which is what created_at columns hold (UTC).
_SQLITE_TS = "%Y-%m-%d %H:%M:%S"


class JobWorkspaceRemovedError(Exception):
    """Raised when a job is being removed by the cleanup right now."""


def touch_job(job_dir: Path) -> None:
    """Mark the job as active now by bumping its workspace folder's mtime."""
    try:
        os.utime(job_dir, None)
    except OSError:
        # Folder already gone (or not ours to touch): nothing to keep alive.
        pass


@contextmanager
def job_in_use(job_id: str, job_dir: Path) -> Iterator[None]:
    """Keep the cleanup away from a job while a request is working on it.

    The workspace's last-activity time is refreshed on the way in and on the
    way out, so the TTL counts from when the request finished.

    Raises:
        JobWorkspaceRemovedError: if the cleanup is deleting this job right now.
    """
    with _state_lock:
        if job_id in _being_removed:
            raise JobWorkspaceRemovedError(job_id)
        _in_use[job_id] = _in_use.get(job_id, 0) + 1
    touch_job(job_dir)
    try:
        yield
    finally:
        touch_job(job_dir)
        with _state_lock:
            _in_use[job_id] -= 1
            if _in_use[job_id] <= 0:
                del _in_use[job_id]


def _claim_for_removal(job_id: str) -> bool:
    with _state_lock:
        if job_id in _in_use:
            return False
        _being_removed.add(job_id)
        return True


def _release_claim(job_id: str) -> None:
    with _state_lock:
        _being_removed.discard(job_id)


def _jobs_in_use() -> set[str]:
    with _state_lock:
        return set(_in_use)


def job_ttl_hours() -> float:
    """Read JOB_TTL_HOURS from the environment.

    Returns:
        The TTL in hours. 0 disables cleanup. Falls back to 24 (with a
        warning) when the value is not a number, not finite, negative, or so
        large that the cutoff date can't be computed.
    """
    raw = os.environ.get("JOB_TTL_HOURS")
    if not raw:
        return DEFAULT_JOB_TTL_HOURS
    try:
        value = float(raw)
        if not math.isfinite(value) or value < 0:
            raise ValueError(raw)
        # Catches finite values like 1e300 that still overflow datetime math.
        datetime.now(timezone.utc) - timedelta(hours=value)
    except (ValueError, OverflowError):
        logger.warning(
            "Invalid JOB_TTL_HOURS=%r, using default of %s hours",
            raw,
            DEFAULT_JOB_TTL_HOURS,
        )
        return DEFAULT_JOB_TTL_HOURS
    return value


async def cleanup_expired_jobs(
    work_root: Path,
    ttl_hours: float,
    *,
    active_job_ids: Collection[str] = (),
    active_org_job_ids: Collection[str] = (),
    now: datetime | None = None,
) -> int:
    """Delete jobs that have been idle for longer than the TTL.

    A job is expired when both its created_at and the last activity on its
    workspace folder (the folder's mtime, set when a scan creates its output
    folders and refreshed by Fix, Verify and the evidence pack through
    job_in_use) are older than the TTL. A job with no created_at is aged by the folder alone, and one whose
    folder is already gone is aged by created_at (or removed if that is NULL
    too).

    Jobs that are still scanning, that belong to an org batch that is still
    running, or that a request is using right now are skipped. Each job is
    removed workspace first, then all its rows in a single transaction. If the
    workspace can't be fully removed the error is logged and the job (rows
    included) is left for the next pass. Org jobs whose child jobs are all gone
    are removed together with their dependency links, and leftover workspace
    folders that never got a jobs row are removed once they are older than the
    TTL.

    Args:
        work_root: Root folder that holds one workspace per job.
        ttl_hours: Idle time after which a job expires. 0 or less disables
            cleanup.
        active_job_ids: Jobs currently being scanned.
        active_org_job_ids: Org batches currently running.
        now: Current time, injectable for tests. Defaults to UTC now.

    Returns:
        Number of expired jobs that were removed.
    """
    if ttl_hours <= 0:
        return 0

    cutoff = (now or datetime.now(timezone.utc)) - timedelta(hours=ttl_hours)
    cutoff_ts = cutoff.strftime(_SQLITE_TS)
    active_jobs = set(active_job_ids)
    active_orgs = set(active_org_job_ids)

    removed_jobs: list[str] = []
    failed_jobs: list[str] = []
    expired_orgs: list[str] = []
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT job_id, org_job_id FROM jobs"
            " WHERE created_at < ? OR created_at IS NULL",
            (cutoff_ts,),
        )
        expired = []
        for job_id, org_job_id in await cursor.fetchall():
            if job_id in active_jobs or org_job_id in active_orgs:
                continue
            # created_at says the job is old, but the workspace may have been
            # used since (Fix, Verify, evidence pack): judge by the folder too.
            if not await asyncio.to_thread(
                _workspace_is_idle, work_root, job_id, cutoff.timestamp()
            ):
                continue
            expired.append(job_id)
        for job_id in expired:
            if await _remove_expired_job(db, work_root, job_id):
                removed_jobs.append(job_id)
            else:
                failed_jobs.append(job_id)

        cursor = await db.execute(
            """
            SELECT id FROM org_jobs
            WHERE (created_at < ? OR created_at IS NULL)
              AND id NOT IN (SELECT org_job_id FROM jobs WHERE org_job_id IS NOT NULL)
            """,
            (cutoff_ts,),
        )
        candidate_orgs = [
            org_id for (org_id,) in await cursor.fetchall() if org_id not in active_orgs
        ]
        for org_id in candidate_orgs:
            try:
                await db.execute(
                    "DELETE FROM dependency_links WHERE org_job_id = ?", (org_id,)
                )
                await db.execute("DELETE FROM org_jobs WHERE id = ?", (org_id,))
                await db.commit()
            except Exception:
                await db.rollback()
                logger.exception("Could not remove expired org job %s", org_id)
            else:
                expired_orgs.append(org_id)

        cursor = await db.execute("SELECT job_id FROM jobs")
        known_jobs = {job_id for (job_id,) in await cursor.fetchall()}
    finally:
        await db.close()

    orphans = await asyncio.to_thread(
        _orphan_workspaces,
        work_root,
        cutoff.timestamp(),
        known_jobs | active_jobs | _jobs_in_use(),
    )
    removed_orphans = 0
    for path in orphans:
        try:
            await asyncio.to_thread(_rmtree, path)
        except OSError:
            logger.exception("Could not remove orphaned workspace %s", path)
        else:
            removed_orphans += 1

    if removed_jobs or failed_jobs or expired_orgs or removed_orphans:
        logger.info(
            "Expired job cleanup: removed %d jobs, %d org jobs and %d orphaned workspaces "
            "idle for more than %s hours; %d jobs could not be removed and will be "
            "retried on the next pass",
            len(removed_jobs),
            len(expired_orgs),
            removed_orphans,
            ttl_hours,
            len(failed_jobs),
        )
    return len(removed_jobs)


async def _remove_expired_job(db, work_root: Path, job_id: str) -> bool:
    """Remove one job's workspace and then all of its rows. True on success.

    The workspace goes first and the rows are deleted together in one
    transaction afterwards, so a failure never leaves the rows gone while files
    are still around: if the folder can't be removed the rows stay and the job
    is picked up again on the next pass (rmtree carries on from whatever is
    left). If the delete fails after the folder is gone it is rolled back, and
    the next pass finishes the job because a missing folder counts as idle.
    Nothing is held open in the database while the folder is being deleted.
    """
    if not _claim_for_removal(job_id):
        logger.info("Skipping expired job %s, it is in use right now", job_id)
        return False
    try:
        try:
            await _remove_workspace(work_root, job_id)
        except OSError:
            logger.exception(
                "Could not remove the workspace of expired job %s, "
                "leaving the job to be retried on the next pass",
                job_id,
            )
            return False
        try:
            await delete_job(db, job_id)
        except Exception:
            logger.exception(
                "Could not delete the rows of expired job %s, "
                "leaving the job to be retried on the next pass",
                job_id,
            )
            return False
        return True
    finally:
        _release_claim(job_id)


def _rmtree(path: Path) -> None:
    """Remove a folder, raising on failure (unlike safe_rmtree)."""
    try:
        shutil.rmtree(path)
    except FileNotFoundError:
        pass


async def _remove_workspace(work_root: Path, job_id: str) -> None:
    try:
        job_dir = safe_job_dir(work_root, job_id)
    except ValueError:
        logger.warning("Skipping workspace removal for invalid job_id %r", job_id)
        return
    # rmtree on a large extracted repo can take a while, keep it off the loop.
    await asyncio.to_thread(_rmtree, job_dir)


def _workspace_is_idle(work_root: Path, job_id: str, cutoff_epoch: float) -> bool:
    """True when the workspace was last touched before the cutoff or is gone."""
    try:
        job_dir = safe_job_dir(work_root, job_id)
        return job_dir.stat().st_mtime < cutoff_epoch
    except FileNotFoundError:
        return True
    except (ValueError, OSError):
        # Invalid id or unreadable folder: leave it alone rather than guess.
        return False


def _orphan_workspaces(
    work_root: Path, cutoff_epoch: float, known_jobs: set[str]
) -> list[Path]:
    if not work_root.is_dir():
        return []
    orphans = []
    for entry in work_root.iterdir():
        if (
            entry.is_dir()
            and not entry.is_symlink()
            and _GENERATED_JOB_ID.match(entry.name)
            and entry.name not in known_jobs
            and (entry / _WORKSPACE_MARKER).is_dir()
            and entry.stat().st_mtime < cutoff_epoch
        ):
            orphans.append(entry)
    return orphans
