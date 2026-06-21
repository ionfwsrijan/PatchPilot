from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List

import aiosqlite
import httpx
from fastapi import (
    BackgroundTasks,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from app.ml.ranker import load_ranker, scoring_function

from .db import (
    get_cwe_distribution,
    get_db,
    get_dependency_diff,
    get_leaderboard_stats,
    get_trend_data,
    init_db,
    upsert_contributor_stat,
)
from .models import (
    DeduplicatedScanResponse,
    Finding,
    FixRequest,
    FixResponse,
    Location,
    OrgJobStatusResponse,
    OrgScanRequest,
    RepoStatus,
    ScanResponse,
    VerifyResponse,
)
from .remediation.engine import propose_fixes
from .reports.evidence_pack import build_evidence_pack
from .reports.pdf_builder import generate_audit_pdf, generate_org_audit_pdf
from .sandbox.verify import verify_repo
from .scanners.entropy import run_entropy
from .scanners.gitleaks import run_gitleaks
from .scanners.osv import run_osv_scanner
from .scanners.semgrep import run_semgrep
from .utils.deduplicator import deduplicate
from .utils.fs import ensure_dir, safe_rmtree, unzip_to_dir

_MAX_UPLOAD_MB_RAW = os.environ.get("MAX_UPLOAD_MB")
RANKER = load_ranker()

try:
    MAX_UPLOAD_MB = int(_MAX_UPLOAD_MB_RAW) if _MAX_UPLOAD_MB_RAW else 100
except ValueError:
    MAX_UPLOAD_MB = 100

MAX_UPLOAD_MB = max(1, MAX_UPLOAD_MB)
MAX_UPLOAD_SIZE = MAX_UPLOAD_MB * 1024 * 1024

logger = logging.getLogger(__name__)
app = FastAPI(title="PatchPilot API", version="0.1.0")

ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

env_origins = os.environ.get("ALLOWED_ORIGINS") or os.environ.get(
    "VITE_API_BASE_URL", ""
)
if env_origins:
    for origin in env_origins.split(","):
        cleaned_origin = origin.strip()
        if cleaned_origin:
            if cleaned_origin.endswith("/"):
                cleaned_origin = cleaned_origin.rstrip("/")
            ALLOWED_ORIGINS.append(cleaned_origin)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

WORK_ROOT = Path(
    os.environ.get("PATCHPILOT_WORKDIR", Path(tempfile.gettempdir()) / "patchpilot")
)
ensure_dir(WORK_ROOT)


@app.on_event("startup")
async def startup():
    await init_db()


@app.get("/health")
def health():
    scanners = {
        "semgrep": shutil.which("semgrep") is not None,
        "osv-scanner": shutil.which("osv-scanner") is not None,
        "gitleaks": shutil.which("gitleaks") is not None,
    }

    healthy = all(scanners.values())

    return {
        "ok": healthy,
        "status": "healthy" if healthy else "degraded",
        "scanners": scanners,
    }


def _prioritize_findings(findings: List[Finding]) -> List[Finding]:
    def score(f: Finding) -> int:
        sev = {"CRITICAL": 100, "HIGH": 80, "MEDIUM": 50, "LOW": 20, "INFO": 5}.get(
            f.severity, 10
        )
        tw = {"dependency": 25, "secret": 35, "sast": 20}.get(f.category, 10)
        return sev + tw

    return sorted(findings, key=score, reverse=True)


def _extract_dependencies(repo_dir: Path) -> List[tuple[str, str]]:
    """
    Lightweight parser to extract dependencies from common manifests.
    Currently supports package.json (Node) and requirements.txt (Python).
    Returns a list of (package_name, version) tuples.
    """
    deps = []
    pkg_json_path = repo_dir / "package.json"
    if pkg_json_path.exists():
        try:
            data = json.loads(pkg_json_path.read_text(encoding="utf-8"))

            all_deps = {
                **data.get("dependencies", {}),
                **data.get("devDependencies", {}),
            }
            for name, version in all_deps.items():
                deps.append((name, str(version)))
        except Exception as e:
            logger.warning("Failed to parse package.json in %s: %s", repo_dir, e)

    req_txt_path = repo_dir / "requirements.txt"
    if req_txt_path.exists():
        try:
            lines = req_txt_path.read_text(encoding="utf-8").splitlines()
            for line in lines:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                match = re.match(r"^([a-zA-Z0-9\-_]+)(?:[=<>~]+(.*))?$", line)
                if match:
                    name = match.group(1)
                    version = match.group(2) or "unknown"
                    deps.append((name, version))
        except Exception as e:
            logger.warning("Failed to parse requirements.txt in %s: %s", repo_dir, e)

    return deps


ACTIVE_SCANS = {}


def _scan_repo_dir(repo_dir: Path, progress_cb=None):
    if progress_cb:
        progress_cb("sast", "in_progress")
    semgrep = run_semgrep(repo_dir)
    if progress_cb:
        progress_cb("sast", "completed")

    if progress_cb:
        progress_cb("dependency", "in_progress")
    osv = run_osv_scanner(repo_dir)
    if progress_cb:
        progress_cb("dependency", "completed")

    if progress_cb:
        progress_cb("secrets", "in_progress")
    gitleaks = run_gitleaks(repo_dir)
    if progress_cb:
        progress_cb("secrets", "completed")

    entropy = run_entropy(repo_dir)

    findings: List[Finding] = []
    findings.extend(semgrep)
    findings.extend(osv)
    findings.extend(gitleaks)
    findings.extend(entropy)

    findings = scoring_function(findings, RANKER)

    if RANKER:
        findings.sort(
            key=lambda f: getattr(f, "ml_score", 0.0),
            reverse=True,
        )
    else:
        findings = _prioritize_findings(findings)

    return semgrep, osv, gitleaks, entropy, findings


def finding_key(f: Finding):
    metadata = f.metadata or {}

    rule_id = (
        metadata.get("check_id")
        or metadata.get("rule")
        or metadata.get("osv_id")
        or f.title
    )

    file_path = f.location.path if f.location else None
    line_number = f.location.start_line if f.location else None

    return (
        rule_id,
        file_path,
        line_number,
    )


def github_zip_url(repo_url: str, ref: str = "main") -> str:
    repo_url = repo_url.strip()
    m = re.match(
        r"^https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$", repo_url, re.IGNORECASE
    )
    if not m:
        raise HTTPException(
            status_code=400, detail="Only GitHub repo URLs are supported right now."
        )
    owner, repo = m.group(1), m.group(2)
    return f"https://github.com/{owner}/{repo}/archive/refs/heads/{ref}.zip"


ALLOWED_REDIRECT_HOSTS = {
    "github.com",
    "codeload.github.com",
    "objects.githubusercontent.com",
}

MAX_REDIRECTS = 5


async def download_to_path(url: str, dest_path: Path, max_retries: int = 5) -> None:
    """
    Download *url* to *dest_path*, following redirects only to hosts in
    ALLOWED_REDIRECT_HOSTS. Implements exponential backoff for GitHub rate limits.
    Now securely streams the download to prevent RAM/Disk exhaustion.
    """
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    timeout = httpx.Timeout(120.0, connect=30.0)
    base_delay = 2.0

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        for attempt in range(max_retries):
            current_url = url
            status_code_for_retry = None

            try:
                for _ in range(MAX_REDIRECTS):
                    parsed = httpx.URL(current_url)
                    if parsed.host not in ALLOWED_REDIRECT_HOSTS:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Redirect to disallowed host '{parsed.host}' was blocked.",
                        )
                    async with client.stream("GET", current_url) as r:
                        if r.status_code in (301, 302, 303, 307, 308):
                            location = r.headers.get("location")
                            if not location:
                                raise HTTPException(
                                    status_code=400,
                                    detail="Redirect missing Location header.",
                                )
                            current_url = str(location)
                            continue

                        if r.status_code in (403, 429):
                            status_code_for_retry = r.status_code
                            break

                        if r.status_code != 200:
                            raise HTTPException(
                                status_code=400,
                                detail=f"Failed to download repo ZIP ({r.status_code}).",
                            )
                        bytes_received = 0
                        chunk_size = 1024 * 1024
                        file_limit_exceeded = False
                        with open(dest_path, "wb") as f:
                            async for chunk in r.aiter_bytes(chunk_size=chunk_size):
                                bytes_received += len(chunk)
                                if bytes_received > MAX_UPLOAD_SIZE:
                                    file_limit_exceeded = True
                                    break
                                f.write(chunk)

                        if file_limit_exceeded:
                            dest_path.unlink(missing_ok=True)
                            raise HTTPException(
                                status_code=413,
                                detail=f"Remote repository exceeds the maximum limit of {MAX_UPLOAD_MB}MB.",
                            )
                        return

                if status_code_for_retry in (403, 429):
                    if attempt == max_retries - 1:
                        raise HTTPException(
                            status_code=429,
                            detail="GitHub API rate limit exceeded after retries.",
                        )

                    jitter = random.uniform(0.5, 1.5)
                    sleep_time = (base_delay * (2**attempt)) + jitter
                    logger.warning(
                        f"Rate limited (status {status_code_for_retry}) on {url}. Retrying in {sleep_time:.2f}s..."
                    )
                    await asyncio.sleep(sleep_time)
                    continue

                raise HTTPException(
                    status_code=400, detail=f"Too many redirects (max {MAX_REDIRECTS})."
                )

            except httpx.RequestError as e:
                if attempt == max_retries - 1:
                    raise HTTPException(
                        status_code=400, detail=f"Network error downloading repo: {e}"
                    )
                jitter = random.uniform(0.5, 1.5)
                await asyncio.sleep((base_delay * (2**attempt)) + jitter)


def _maybe_use_single_top_folder(repo_dir: Path) -> Path:
    """
    If the extracted folder contains exactly one top-level directory (typical GitHub ZIP),
    treat that directory as the scan root.
    """
    try:
        dirs = [p for p in repo_dir.iterdir() if p.is_dir()]
        files = [p for p in repo_dir.iterdir() if p.is_file()]
    except FileNotFoundError:
        return repo_dir

    if len(dirs) == 1 and len(files) == 0:
        return dirs[0]

    return repo_dir


async def _run_single_scan_task(
    job_id: str, project_name: str, scan_method: str, scan_root: Path
):
    def update_progress(phase, status):
        if job_id in ACTIVE_SCANS:
            ACTIVE_SCANS[job_id][phase] = status

    ACTIVE_SCANS[job_id] = {
        "sast": "pending",
        "dependency": "pending",
        "secrets": "pending",
        "status": "running",
    }

    try:
        db = await get_db()
        try:
            await db.execute(
                "INSERT INTO jobs (job_id, project_name, scan_method) VALUES (?, ?, ?)",
                (job_id, project_name, scan_method),
            )
            await db.commit()
        finally:
            await db.close()

        semgrep, osv, gitleaks, entropy, findings = await run_in_threadpool(
            _scan_repo_dir, scan_root, update_progress
        )

        disable_dedup = os.environ.get("DISABLE_DEDUP", "false").lower() in {
            "1",
            "true",
            "yes",
        }

        try:
            epsilon = float(os.environ.get("DEDUP_EPSILON", "0.15"))
        except ValueError:
            epsilon = 0.15

        if disable_dedup:
            dedup_findings = findings
        else:
            dedup_findings = deduplicate(findings, epsilon=epsilon)

        db = await get_db()
        try:
            rows = []
            for f in dedup_findings:
                engine = (f.metadata or {}).get("engine")
                scanner = {"osv-scanner": "osv"}.get(engine, engine)
                rule_id = (
                    (f.metadata or {}).get("check_id")
                    or (f.metadata or {}).get("rule")
                    or (f.metadata or {}).get("osv_id")
                    or f.title
                )
                file_path = f.location.path if f.location else None
                line_number = f.location.start_line if f.location else None
                message = f.description or f.title
                pkg_info = (f.metadata or {}).get("package") or {}
                pkg_name = pkg_info.get("name")
                pkg_version = pkg_info.get("version")
                rows.append(
                    (
                        str(uuid.uuid4()),
                        job_id,
                        rule_id,
                        f.severity,
                        f.category,
                        file_path,
                        line_number,
                        None,
                        scanner,
                        message,
                        pkg_name,
                        pkg_version,
                    )
                )
            if rows:
                await db.executemany(
                    "INSERT INTO findings (id, job_id, rule_id, severity, category, file_path, line_number, cwe, scanner, message, package_name, package_version) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    rows,
                )
            await db.commit()
        finally:
            await db.close()

        if job_id in ACTIVE_SCANS:
            ACTIVE_SCANS[job_id]["status"] = "completed"
            ACTIVE_SCANS[job_id]["findings_count"] = len(dedup_findings)
            ACTIVE_SCANS[job_id]["raw_finding_count"] = len(findings)
    except Exception:
        logger.exception("Failed scan task for %s", job_id)
        if job_id in ACTIVE_SCANS:
            ACTIVE_SCANS[job_id]["status"] = "failed"


@app.post("/scan")
async def scan(
    request: Request,
    background_tasks: BackgroundTasks,
    project: UploadFile = File(...),
    project_name: str = Form("project"),
):
    content_length = request.headers.get("content-length")
    try:
        content_length = int(content_length) if content_length else None
    except ValueError:
        content_length = None

    if content_length and content_length > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"Header indicates file is too large. Maximum upload size is {MAX_UPLOAD_MB}MB.",
        )

    job_id = next(tempfile._get_candidate_names())
    job_dir = WORK_ROOT / job_id
    ensure_dir(job_dir)
    archive_path = job_dir / project.filename
    bytes_received = 0
    chunk_size = 1024 * 1024

    try:
        with open(archive_path, "wb") as f:
            while chunk := await project.read(chunk_size):
                bytes_received += len(chunk)
                if bytes_received > MAX_UPLOAD_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Actual file size exceeds the maximum limit of {MAX_UPLOAD_MB}MB.",
                    )
                f.write(chunk)
    except HTTPException:
        safe_rmtree(job_dir)
        raise
    except Exception as e:
        safe_rmtree(job_dir)
        raise HTTPException(status_code=400, detail=f"Error saving upload: {e}")

    repo_dir = job_dir / "repo"
    ensure_dir(repo_dir)

    try:
        unzip_to_dir(archive_path, repo_dir)
    except Exception as e:
        safe_rmtree(job_dir)
        raise HTTPException(status_code=400, detail=f"Invalid zip upload: {e}")

    scan_root = _maybe_use_single_top_folder(repo_dir)
    background_tasks.add_task(
        _run_single_scan_task, job_id, project_name, "zip", scan_root
    )
    return {"job_id": job_id, "project_name": project_name, "status": "running"}


@app.post("/scan-url")
async def scan_url(
    background_tasks: BackgroundTasks,
    repo_url: str = Form(...),
    ref: str = Form("main"),
    project_name: str = Form("project"),
):
    job_id = next(tempfile._get_candidate_names())
    job_dir = WORK_ROOT / job_id
    ensure_dir(job_dir)
    archive_path = job_dir / "repo.zip"
    repo_dir = job_dir / "repo"
    ensure_dir(repo_dir)
    zip_url = github_zip_url(repo_url, ref=ref)

    try:
        await download_to_path(zip_url, archive_path)
        unzip_to_dir(archive_path, repo_dir)
    except HTTPException:
        safe_rmtree(job_dir)
        raise
    except Exception as e:
        safe_rmtree(job_dir)
        raise HTTPException(status_code=400, detail=f"Import from URL failed: {e}")

    scan_root = _maybe_use_single_top_folder(repo_dir)
    background_tasks.add_task(
        _run_single_scan_task, job_id, project_name, "url", scan_root
    )
    return {"job_id": job_id, "project_name": project_name, "status": "running"}


@app.get("/api/scans/{job_id}/stream")
async def stream_single_scan_status(job_id: str):
    async def event_generator():
        while True:
            if job_id not in ACTIVE_SCANS:
                yield f"data: {json.dumps({'error': 'Job not found'})}\n\n"
                break
            state = ACTIVE_SCANS[job_id]
            yield f"data: {json.dumps(state)}\n\n"
            if state["status"] in ["completed", "failed"]:
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/fix", response_model=FixResponse)
def fix(req: FixRequest):
    job_dir = WORK_ROOT / req.job_id
    repo_dir = job_dir / "repo"
    if not repo_dir.exists():
        raise HTTPException(status_code=404, detail="Unknown job_id")

    repo_dir = _maybe_use_single_top_folder(repo_dir)
    fixes = propose_fixes(repo_dir, req.finding_ids)

    return FixResponse(job_id=req.job_id, fixes=fixes)


async def get_baseline_findings(job_id: str):
    db = await get_db()
    try:
        cursor = await db.execute(
            """
            SELECT rule_id, file_path, line_number
            FROM findings
            WHERE job_id = ?
            """,
            (job_id,),
        )
        rows = await cursor.fetchall()

        return {
            (
                row[0],
                row[1],
                row[2],
            )
            for row in rows
        }
    finally:
        await db.close()


@app.post("/verify", response_model=VerifyResponse)
async def verify(job_id: str = Form(...)):
    job_dir = WORK_ROOT / job_id
    repo_dir = job_dir / "repo"
    if not repo_dir.exists():
        raise HTTPException(status_code=404, detail="Unknown job_id")

    repo_dir = _maybe_use_single_top_folder(repo_dir)

    result = verify_repo(repo_dir)

    baseline_findings = await get_baseline_findings(job_id)

    _, _, _, _, findings = _scan_repo_dir(repo_dir)

    current_findings = {finding_key(f) for f in findings}

    new_findings = current_findings - baseline_findings

    new_issues_introduced = len(new_findings)
    logger.info(
        "Verify detected %d new findings for job %s",
        new_issues_introduced,
        job_id,
    )

    passed = 1 if result.ok and new_issues_introduced == 0 else 0
    try:
        db = await get_db()
        try:
            await db.execute(
                """
                INSERT INTO verify_outcomes
                (id, job_id, passed, new_issues_introduced)
                VALUES (?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    job_id,
                    passed,
                    new_issues_introduced,
                ),
            )
            await db.commit()
        finally:
            await db.close()
    except Exception:
        logger.exception("Failed to persist verify outcome for job %s", job_id)
    return result


@app.post("/evidence-pack")
def evidence_pack(job_id: str = Form(...), project_name: str = Form("project")):
    job_dir = WORK_ROOT / job_id
    repo_dir = job_dir / "repo"
    if not repo_dir.exists():
        raise HTTPException(status_code=404, detail="Unknown job_id")

    repo_dir = _maybe_use_single_top_folder(repo_dir)

    out_dir = job_dir / "out"
    ensure_dir(out_dir)

    pack_path = build_evidence_pack(
        repo_dir=repo_dir, out_dir=out_dir, project_name=project_name, job_id=job_id
    )
    return FileResponse(
        path=str(pack_path), filename=pack_path.name, media_type="application/zip"
    )


@app.get("/api/scans/{job_id}/report/pdf", tags=["Reports"])
async def download_audit_pdf(job_id: str):
    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT project_name FROM jobs WHERE job_id = ?", (job_id,)
        )
        job_row = await cur.fetchone()

        if job_row is None:
            raise HTTPException(
                status_code=404, detail=f"No job found with id '{job_id}'"
            )

        project_name = job_row[0]

        cur = await db.execute(
            """
            SELECT id, rule_id, severity, category, file_path, line_number, message
            FROM findings
            WHERE job_id = ?
            """,
            (job_id,),
        )
        columns = [col[0] for col in cur.description]
        rows = await cur.fetchall()
    finally:
        await db.close()

    findings_list = []
    for row in rows:
        row_dict = dict(zip(columns, row))

        loc = None
        if row_dict["file_path"]:
            loc = Location(
                path=row_dict["file_path"], start_line=row_dict["line_number"]
            )

        findings_list.append(
            Finding(
                id=row_dict["id"],
                title=row_dict["rule_id"] or "Unknown",
                severity=row_dict["severity"] or "INFO",
                category=row_dict["category"] or "Unknown",
                location=loc,
                description=row_dict["message"] or "",
            )
        )

    scan_data = ScanResponse(
        job_id=job_id,
        project_name=project_name,
        repo_path="Repository",
        findings=findings_list,
        scanners={},
    )

    pdf_bytes = generate_audit_pdf(scan_data)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=PatchPilot-Audit-{job_id}.pdf"
        },
    )


@app.get("/jobs/{job_id}/findings")
async def get_findings(job_id: str):
    db = await get_db()
    try:
        cur = await db.execute("SELECT job_id FROM jobs WHERE job_id = ?", (job_id,))
        job_row = await cur.fetchone()

        if job_row is None:
            raise HTTPException(
                status_code=404, detail=f"No job found with id '{job_id}'"
            )

        cur = await db.execute(
            """
            SELECT id, rule_id, severity, category, file_path,
                   line_number, cwe, scanner, message, package_name, package_version, created_at
            FROM findings
            WHERE job_id = ?
            ORDER BY created_at
            """,
            (job_id,),
        )
        columns = [col[0] for col in cur.description]
        rows = await cur.fetchall()
    finally:
        await db.close()

    findings = [dict(zip(columns, row)) for row in rows]
    return {"job_id": job_id, "finding_count": len(findings), "findings": findings}


@app.get("/jobs/{job_id}/verify")
async def get_verify(job_id: str):
    db = await get_db()
    try:
        cur = await db.execute("SELECT job_id FROM jobs WHERE job_id = ?", (job_id,))
        job_row = await cur.fetchone()

        if job_row is None:
            raise HTTPException(
                status_code=404, detail=f"No job found with id '{job_id}'"
            )

        cur = await db.execute(
            """
            SELECT id, job_id, passed, new_issues_introduced, verified_at
            FROM verify_outcomes
            WHERE job_id = ?
            ORDER BY verified_at DESC
            LIMIT 1
            """,
            (job_id,),
        )
        columns = [col[0] for col in cur.description]
        row = await cur.fetchone()
    finally:
        await db.close()

    if row is None:
        raise HTTPException(
            status_code=404, detail=f"No verify outcome recorded yet for job '{job_id}'"
        )

    return dict(zip(columns, row))


@app.delete("/jobs/{job_id}")
def delete_job(job_id: str):
    job_dir = WORK_ROOT / job_id
    if job_dir.exists():
        safe_rmtree(job_dir)
    return {"deleted": True}


@app.get("/trends")
async def get_trends_endpoint(limit: int = 6):
    """Fetches historical trend data for the frontend dashboard."""
    data = await get_trend_data(limit)
    return data


@app.get("/cwe-distribution")
async def cwe_distribution_endpoint():
    """Fetches the vulnerability distribution for the frontend donut chart."""
    data = await get_cwe_distribution()
    return data


@app.get("/dependency-diff")
async def dependency_diff_endpoint():
    data = await get_dependency_diff()
    return data


class LeaderboardUpdateRequest(BaseModel):
    github_username: str = Field(
        ...,
        max_length=39,
        pattern=r"^[a-zA-Z0-9](?:-?[a-zA-Z0-9])*$",
        description="GitHub username must be max 39 chars, alphanumeric or single hyphens.",
    )
    pr_description: str = ""
    fixes_passed: int = 0
    is_pr_merged: bool = False


@app.get("/leaderboard")
async def leaderboard_endpoint():
    data = await get_leaderboard_stats()
    return data


@app.post("/leaderboard/update")
async def update_leaderboard_endpoint(req: LeaderboardUpdateRequest):
    pattern = r"(?i)(?:close|closes|closed|fix|fixes|fixed|resolve|resolves|resolved)\s+#(\d+)"
    matches = re.findall(pattern, req.pr_description)

    findings_closed = len(set(matches))
    prs_merged = 1 if req.is_pr_merged else 0

    await upsert_contributor_stat(
        username=req.github_username,
        findings=findings_closed,
        fixes=req.fixes_passed,
        prs=prs_merged,
    )

    return {
        "status": "success",
        "github_username": req.github_username,
        "stats_added": {
            "findings_closed": findings_closed,
            "fixes_passed": req.fixes_passed,
            "prs_merged": prs_merged,
        },
    }


async def fetch_org_repos(org_name: str) -> List[dict]:
    url = f"https://api.github.com/orgs/{org_name}/repos?per_page=100&sort=updated"
    headers = {"Accept": "application/vnd.github.v3+json"}
    token = os.environ.get("GITHUB_PAT")
    if token:
        headers["Authorization"] = f"token {token}"
    timeout = httpx.Timeout(30.0, connect=10.0)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, headers=headers, follow_redirects=True)
            if resp.status_code != 200:
                raise HTTPException(status_code=400, detail="Failed to fetch org repos")
            repos = resp.json()
            return [r for r in repos if not r.get("archived")][:20]
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=504, detail=f"GitHub API request failed or timed out: {e}"
        )


async def _run_repo_scan_task(
    sem: asyncio.Semaphore,
    job_id: str,
    repo_url: str,
    ref: str,
    project_name: str,
    org_job_id: str,
):
    async with sem:
        try:
            db = await get_db()
            try:
                db.row_factory = aiosqlite.Row
                cur = await db.execute(
                    "SELECT status FROM org_jobs WHERE id = ?", (org_job_id,)
                )
                org_row = await cur.fetchone()

                if org_row and org_row["status"] == "aborted":
                    await db.execute(
                        "UPDATE jobs SET status = 'aborted' WHERE job_id = ?", (job_id,)
                    )
                    await db.commit()
                    return

                await db.execute(
                    "UPDATE jobs SET status = 'scanning' WHERE job_id = ?", (job_id,)
                )
                await db.commit()
            finally:
                await db.close()

            job_dir = WORK_ROOT / job_id
            ensure_dir(job_dir)
            archive_path = job_dir / "repo.zip"
            repo_dir = job_dir / "repo"
            ensure_dir(repo_dir)

            zip_url = github_zip_url(repo_url, ref=ref)
            await download_to_path(zip_url, archive_path)
            unzip_to_dir(archive_path, repo_dir)

            scan_root = _maybe_use_single_top_folder(repo_dir)
            semgrep, osv, gitleaks, entropy, findings = _scan_repo_dir(scan_root)

            deps = _extract_dependencies(scan_root)

            db = await get_db()
            try:
                rows = []
                for f in findings:
                    engine = (f.metadata or {}).get("engine")
                    scanner = {"osv-scanner": "osv"}.get(engine, engine)
                    rule_id = (
                        (f.metadata or {}).get("check_id")
                        or (f.metadata or {}).get("rule")
                        or (f.metadata or {}).get("osv_id")
                        or f.title
                    )
                    file_path = f.location.path if f.location else None
                    line_number = f.location.start_line if f.location else None
                    message = f.description or f.title
                    pkg_info = (f.metadata or {}).get("package") or {}
                    pkg_name = pkg_info.get("name")
                    pkg_version = pkg_info.get("version")

                    rows.append(
                        (
                            str(uuid.uuid4()),
                            job_id,
                            rule_id,
                            f.severity,
                            f.category,
                            file_path,
                            line_number,
                            None,
                            scanner,
                            message,
                            pkg_name,
                            pkg_version,
                        )
                    )

                if rows:
                    await db.executemany(
                        "INSERT INTO findings (id, job_id, rule_id, severity, category, file_path, line_number, cwe, scanner, message, package_name, package_version) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        rows,
                    )

                dep_rows = []
                for pkg_n, pkg_v in deps:
                    dep_rows.append(
                        (str(uuid.uuid4()), org_job_id, project_name, pkg_n, pkg_v)
                    )

                if dep_rows:
                    await db.executemany(
                        "INSERT INTO dependency_links (id, org_job_id, project_name, package_name, package_version) VALUES (?, ?, ?, ?, ?)",
                        dep_rows,
                    )

                await db.execute(
                    "UPDATE jobs SET status = 'completed' WHERE job_id = ?", (job_id,)
                )
                await db.commit()
            finally:
                await db.close()
        except Exception:
            logger.exception("Failed repo scan task for job %s", job_id)
            db = await get_db()
            try:
                await db.execute(
                    "UPDATE jobs SET status = 'failed' WHERE job_id = ?", (job_id,)
                )
                await db.commit()
            finally:
                await db.close()


async def _run_org_batch(org_job_id: str, repos: List[dict]):
    db = await get_db()
    try:
        await db.execute(
            "UPDATE org_jobs SET status = 'scanning' WHERE id = ?", (org_job_id,)
        )
        await db.commit()
    finally:
        await db.close()

    sem = asyncio.Semaphore(5)
    tasks = []

    for r in repos:
        repo_url = r["html_url"]
        ref = r["default_branch"]
        project_name = r["name"]
        job_id = next(tempfile._get_candidate_names())

        db = await get_db()
        try:
            await db.execute(
                "INSERT INTO jobs (job_id, project_name, scan_method, org_job_id, status) VALUES (?, ?, ?, ?, ?)",
                (job_id, project_name, "org_batch", org_job_id, "pending"),
            )
            await db.commit()
        finally:
            await db.close()

        tasks.append(
            _run_repo_scan_task(sem, job_id, repo_url, ref, project_name, org_job_id)
        )

    await asyncio.gather(*tasks, return_exceptions=True)

    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT status FROM org_jobs WHERE id = ?", (org_job_id,)
        )
        row = await cur.fetchone()

        if row and row[0] != "aborted":
            await db.execute(
                "UPDATE org_jobs SET status = 'completed' WHERE id = ?", (org_job_id,)
            )
            await db.commit()
    finally:
        await db.close()


@app.post("/api/scans/org")
async def scan_org(req: OrgScanRequest, background_tasks: BackgroundTasks):
    m = re.match(
        r"^https?://github\.com/([^/]+)/?$", req.org_url.strip(), re.IGNORECASE
    )
    if not m:
        raise HTTPException(status_code=400, detail="Invalid GitHub Organization URL")
    org_name = m.group(1)

    repos = await fetch_org_repos(org_name)
    if not repos:
        raise HTTPException(
            status_code=400, detail="No public repositories found for this organization"
        )

    org_job_id = str(uuid.uuid4())

    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO org_jobs (id, org_name, status) VALUES (?, ?, ?)",
            (org_job_id, org_name, "pending"),
        )
        await db.commit()
    finally:
        await db.close()

    background_tasks.add_task(_run_org_batch, org_job_id, repos)

    return {"org_job_id": org_job_id, "org_name": org_name, "repo_count": len(repos)}


@app.get("/api/scans/org/{org_job_id}/status", response_model=OrgJobStatusResponse)
async def get_org_status(org_job_id: str):
    db = await get_db()
    try:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT status FROM org_jobs WHERE id = ?", (org_job_id,)
        )
        org_row = await cur.fetchone()
        if not org_row:
            raise HTTPException(status_code=404, detail="Org job not found")

        cur = await db.execute(
            "SELECT job_id, project_name, status FROM jobs WHERE org_job_id = ?",
            (org_job_id,),
        )
        job_rows = await cur.fetchall()
    finally:
        await db.close()

    repos = [
        RepoStatus(
            job_id=r["job_id"], project_name=r["project_name"], status=r["status"]
        )
        for r in job_rows
    ]

    return OrgJobStatusResponse(
        org_job_id=org_job_id, status=org_row["status"], repos=repos
    )


@app.post("/api/scans/org/{org_job_id}/abort")
async def abort_org_scan(org_job_id: str, mode: str = Query("pending")):
    for attempt in range(5):
        try:
            db = await get_db()
            try:
                await db.execute(
                    "UPDATE org_jobs SET status = 'aborted' WHERE id = ? AND status != 'completed'",
                    (org_job_id,),
                )
                if mode == "force":
                    await db.execute(
                        "UPDATE jobs SET status = 'aborted' WHERE org_job_id = ? AND status IN ('pending', 'scanning')",
                        (org_job_id,),
                    )
                else:
                    await db.execute(
                        "UPDATE jobs SET status = 'aborted' WHERE org_job_id = ? AND status = 'pending'",
                        (org_job_id,),
                    )

                await db.commit()
                return {"status": "aborted", "org_job_id": org_job_id, "mode": mode}
            finally:
                await db.close()
        except Exception as e:
            if "locked" in str(e).lower() and attempt < 4:
                import asyncio

                await asyncio.sleep(1)
                continue
            raise HTTPException(status_code=500, detail=f"Database lock timeout: {e}")


@app.get("/api/scans/org/{org_job_id}/stream")
async def stream_org_status(org_job_id: str):
    async def event_generator():
        while True:
            db = await get_db()
            try:
                db.row_factory = aiosqlite.Row
                cur = await db.execute(
                    "SELECT status FROM org_jobs WHERE id = ?", (org_job_id,)
                )
                org_row = await cur.fetchone()

                if not org_row:
                    yield f"data: {json.dumps({'error': 'Org job not found'})}\n\n"
                    break

                cur = await db.execute(
                    "SELECT job_id, project_name, status FROM jobs WHERE org_job_id = ?",
                    (org_job_id,),
                )
                job_rows = await cur.fetchall()
            finally:
                await db.close()

            repos = [
                {
                    "job_id": r["job_id"],
                    "project_name": r["project_name"],
                    "status": r["status"],
                }
                for r in job_rows
            ]
            payload = {
                "org_job_id": org_job_id,
                "status": org_row["status"],
                "repos": repos,
            }

            yield f"data: {json.dumps(payload)}\n\n"
            if org_row["status"] in ["completed", "failed"]:
                break

            if org_row["status"] == "aborted":
                is_scanning = any(r["status"] == "scanning" for r in job_rows)
                if not is_scanning:
                    break

            await asyncio.sleep(1.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/api/scans/org/{org_job_id}/summary")
async def get_org_summary(org_job_id: str):
    db = await get_db()
    try:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed
            FROM jobs 
            WHERE org_job_id = ?
            """,
            (org_job_id,),
        )
        repo_stats = await cur.fetchone()

        cur = await db.execute(
            """
            SELECT f.severity, COUNT(f.id) as count
            FROM findings f
            JOIN jobs j ON f.job_id = j.job_id
            WHERE j.org_job_id = ?
            GROUP BY f.severity
            """,
            (org_job_id,),
        )
        severity_rows = await cur.fetchall()
        severities = {r["severity"].lower(): r["count"] for r in severity_rows}

        cur = await db.execute(
            """
            SELECT j.project_name as repo_name, COUNT(f.id) as count
            FROM findings f
            JOIN jobs j ON f.job_id = j.job_id
            WHERE j.org_job_id = ?
            GROUP BY j.project_name
            ORDER BY count DESC
            LIMIT 5
            """,
            (org_job_id,),
        )
        top_vulnerable = [
            {"repo_name": r["repo_name"], "count": r["count"]}
            for r in await cur.fetchall()
        ]

        return {
            "total_repositories": repo_stats["total"] or 0,
            "completed_repositories": repo_stats["completed"] or 0,
            "failed_repositories": repo_stats["failed"] or 0,
            "severity_distribution": severities,
            "top_vulnerable_repositories": top_vulnerable,
        }
    finally:
        await db.close()


@app.get("/api/scans/org/{org_job_id}/findings")
async def get_org_findings(org_job_id: str):
    db = await get_db()
    try:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT 
                f.id, 
                j.project_name as repo_name, 
                f.rule_id as title, 
                f.message as description, 
                f.severity, 
                f.file_path, 
                f.line_number, 
                f.cwe
            FROM findings f
            JOIN jobs j ON f.job_id = j.job_id
            WHERE j.org_job_id = ?
            ORDER BY 
                CASE f.severity 
                    WHEN 'CRITICAL' THEN 1 
                    WHEN 'HIGH' THEN 2 
                    WHEN 'MEDIUM' THEN 3 
                    WHEN 'LOW' THEN 4 
                    ELSE 5 
                END
            """,
            (org_job_id,),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


@app.get("/api/scans/org/{org_job_id}/report/pdf", tags=["Reports"])
async def download_org_audit_pdf(org_job_id: str):
    db = await get_db()
    try:
        db.row_factory = aiosqlite.Row

        cur = await db.execute(
            "SELECT org_name FROM org_jobs WHERE id = ?", (org_job_id,)
        )
        org_row = await cur.fetchone()
        if not org_row:
            raise HTTPException(status_code=404, detail="Organization job not found")
        org_name = org_row["org_name"]
        cur = await db.execute(
            """
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed
            FROM jobs 
            WHERE org_job_id = ?
            """,
            (org_job_id,),
        )
        repo_stats = await cur.fetchone()

        cur = await db.execute(
            """
            SELECT f.severity, COUNT(f.id) as count
            FROM findings f
            JOIN jobs j ON f.job_id = j.job_id
            WHERE j.org_job_id = ?
            GROUP BY f.severity
            """,
            (org_job_id,),
        )
        severity_rows = await cur.fetchall()
        severities = {r["severity"].lower(): r["count"] for r in severity_rows}

        cur = await db.execute(
            """
            SELECT j.project_name as repo_name, COUNT(f.id) as count
            FROM findings f
            JOIN jobs j ON f.job_id = j.job_id
            WHERE j.org_job_id = ?
            GROUP BY j.project_name
            ORDER BY count DESC
            LIMIT 5
            """,
            (org_job_id,),
        )
        top_vulnerable = [
            {"repo_name": r["repo_name"], "count": r["count"]}
            for r in await cur.fetchall()
        ]

        summary = {
            "total_repositories": repo_stats["total"] or 0,
            "completed_repositories": repo_stats["completed"] or 0,
            "failed_repositories": repo_stats["failed"] or 0,
            "severity_distribution": severities,
            "top_vulnerable_repositories": top_vulnerable,
        }
        cur = await db.execute(
            """
            SELECT 
                f.id, 
                j.project_name as repo_name, 
                f.rule_id as title, 
                f.message as description, 
                f.severity, 
                f.file_path, 
                f.line_number, 
                f.cwe
            FROM findings f
            JOIN jobs j ON f.job_id = j.job_id
            WHERE j.org_job_id = ?
            ORDER BY 
                CASE f.severity 
                    WHEN 'CRITICAL' THEN 1 
                    WHEN 'HIGH' THEN 2 
                    WHEN 'MEDIUM' THEN 3 
                    WHEN 'LOW' THEN 4 
                    ELSE 5 
                END
            """,
            (org_job_id,),
        )
        findings = [dict(r) for r in await cur.fetchall()]

    finally:
        await db.close()

    pdf_bytes = generate_org_audit_pdf(org_job_id, org_name, summary, findings)

    safe_org_name = "".join(
        c for c in org_name if c.isalnum() or c in ("-", "_")
    ).rstrip()
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    filename = f"PatchPilot-Org-Audit-{safe_org_name}-{date_str}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/scans/org/{org_job_id}/blast-radius", tags=["Organization"])
async def get_blast_radius(org_job_id: str):
    db = await get_db()
    try:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT id FROM org_jobs WHERE id = ?", (org_job_id,))
        if not await cur.fetchone():
            raise HTTPException(status_code=404, detail="Organization job not found")

        cur = await db.execute(
            "SELECT project_name, package_name FROM dependency_links WHERE org_job_id = ?",
            (org_job_id,),
        )
        edges = await cur.fetchall()
        cur = await db.execute(
            """
            SELECT DISTINCT f.package_name 
            FROM findings f
            JOIN jobs j ON f.job_id = j.job_id
            WHERE j.org_job_id = ? AND f.category = 'dependency' AND f.package_name IS NOT NULL
            """,
            (org_job_id,),
        )
        vulnerable_pkgs = {row["package_name"] for row in await cur.fetchall()}

    finally:
        await db.close()

    nodes_dict = {}
    links = []

    for edge in edges:
        repo = edge["project_name"]
        pkg = edge["package_name"]
        if repo not in nodes_dict:
            nodes_dict[repo] = {"id": repo, "type": "repo", "vulnerable": False}

        if pkg not in nodes_dict:
            is_vuln = pkg in vulnerable_pkgs
            nodes_dict[pkg] = {"id": pkg, "type": "package", "vulnerable": is_vuln}

        links.append({"source": repo, "target": pkg})

    return {"nodes": list(nodes_dict.values()), "links": links}
