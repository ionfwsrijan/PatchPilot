"""Automatic cleanup of expired scan workspaces and their database rows."""

from __future__ import annotations

import asyncio
import logging
import os
import re
from collections.abc import Collection
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .db import delete_job, get_db
from .utils.fs import safe_job_dir, safe_rmtree

logger = logging.getLogger(__name__)

DEFAULT_JOB_TTL_HOURS = 24.0
CLEANUP_INTERVAL_SECONDS = 3600

# Job ids come from tempfile._get_candidate_names(): 8 chars of [a-z0-9_].
# Workspace folders without a jobs row are only removed when they match this,
# so a PATCHPILOT_WORKDIR pointed at a shared folder can't lose unrelated dirs.
_GENERATED_JOB_ID = re.compile(r"^[a-z0-9_]{8}$")

# SQLite's datetime('now') format, which is what created_at columns hold (UTC).
_SQLITE_TS = "%Y-%m-%d %H:%M:%S"


def job_ttl_hours() -> float:
    """Read JOB_TTL_HOURS from the environment.

    Returns:
        The TTL in hours. Falls back to 24 when unset or not a number.
        A value of 0 or less disables cleanup.
    """
    raw = os.environ.get("JOB_TTL_HOURS")
    if not raw:
        return DEFAULT_JOB_TTL_HOURS
    try:
        return float(raw)
    except ValueError:
        logger.warning(
            "Invalid JOB_TTL_HOURS=%r, using default of %s hours",
            raw,
            DEFAULT_JOB_TTL_HOURS,
        )
        return DEFAULT_JOB_TTL_HOURS


async def cleanup_expired_jobs(
    work_root: Path,
    ttl_hours: float,
    *,
    active_job_ids: Collection[str] = (),
    active_org_job_ids: Collection[str] = (),
    now: datetime | None = None,
) -> int:
    """Delete jobs older than the TTL, along with their workspace and rows.

    Jobs that are still scanning, or that belong to an org batch that is still
    running, are skipped even when they are past the TTL. Org jobs whose child
    jobs are all gone are removed together with their dependency links, and
    leftover workspace folders that never got a jobs row are removed once they
    are older than the TTL.

    Args:
        work_root: Root folder that holds one workspace per job.
        ttl_hours: Age after which a job expires. 0 or less disables cleanup.
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

    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT job_id, org_job_id FROM jobs WHERE created_at < ?", (cutoff_ts,)
        )
        expired = [
            job_id
            for job_id, org_job_id in await cursor.fetchall()
            if job_id not in active_jobs and org_job_id not in active_orgs
        ]
        for job_id in expired:
            await _remove_workspace(work_root, job_id)
            await delete_job(db, job_id)

        cursor = await db.execute(
            """
            SELECT id FROM org_jobs
            WHERE created_at < ?
              AND id NOT IN (SELECT org_job_id FROM jobs WHERE org_job_id IS NOT NULL)
            """,
            (cutoff_ts,),
        )
        expired_orgs = [
            org_id for (org_id,) in await cursor.fetchall() if org_id not in active_orgs
        ]
        for org_id in expired_orgs:
            await db.execute(
                "DELETE FROM dependency_links WHERE org_job_id = ?", (org_id,)
            )
            await db.execute("DELETE FROM org_jobs WHERE id = ?", (org_id,))
        await db.commit()

        cursor = await db.execute("SELECT job_id FROM jobs")
        known_jobs = {job_id for (job_id,) in await cursor.fetchall()}
    finally:
        await db.close()

    orphans = await asyncio.to_thread(
        _orphan_workspaces, work_root, cutoff.timestamp(), known_jobs | active_jobs
    )
    for path in orphans:
        await asyncio.to_thread(safe_rmtree, path)

    if expired or expired_orgs or orphans:
        logger.info(
            "Expired job cleanup: removed %d jobs, %d org jobs and %d orphaned workspaces "
            "older than %s hours",
            len(expired),
            len(expired_orgs),
            len(orphans),
            ttl_hours,
        )
    return len(expired)


async def _remove_workspace(work_root: Path, job_id: str) -> None:
    try:
        job_dir = safe_job_dir(work_root, job_id)
    except ValueError:
        logger.warning("Skipping workspace removal for invalid job_id %r", job_id)
        return
    # rmtree on a large extracted repo can take a while, keep it off the loop.
    await asyncio.to_thread(safe_rmtree, job_dir)


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
            and entry.stat().st_mtime < cutoff_epoch
        ):
            orphans.append(entry)
    return orphans
