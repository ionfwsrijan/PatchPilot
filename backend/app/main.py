from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import List

import httpx
from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

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
from .models import Finding, FixRequest, FixResponse, ScanResponse, VerifyResponse
from .remediation.engine import propose_fixes
from .reports.evidence_pack import build_evidence_pack
from .sandbox.verify import verify_repo
from .scanners.entropy import run_entropy
from .scanners.gitleaks import run_gitleaks
from .scanners.osv import run_osv_scanner
from .scanners.semgrep import run_semgrep
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
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


def _scan_repo_dir(repo_dir: Path):
    semgrep = run_semgrep(repo_dir)
    osv = run_osv_scanner(repo_dir)
    gitleaks = run_gitleaks(repo_dir)
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


async def download_to_path(url: str, dest_path: Path) -> None:
    """
    Download *url* to *dest_path*, following redirects only to hosts in
    ALLOWED_REDIRECT_HOSTS.  Blindly following redirects (follow_redirects=True)
    would allow a crafted URL to redirect the server to an internal address
    (e.g. cloud-metadata at 169.254.169.254), enabling SSRF.
    """
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    timeout = httpx.Timeout(120.0, connect=30.0)

    current_url = url
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        for _ in range(MAX_REDIRECTS):
            parsed = httpx.URL(current_url)
            if parsed.host not in ALLOWED_REDIRECT_HOSTS:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Redirect to disallowed host '{parsed.host}' was blocked. "
                        f"Only {sorted(ALLOWED_REDIRECT_HOSTS)} are permitted."
                    ),
                )

            r = await client.get(current_url)

            if r.status_code in (301, 302, 303, 307, 308):
                location = r.headers.get("location")
                if not location:
                    raise HTTPException(
                        status_code=400,
                        detail="Redirect response missing Location header.",
                    )
                current_url = str(r.headers["location"])
                continue

            if r.status_code != 200:
                raise HTTPException(
                    status_code=400,
                    detail=f"Failed to download repo ZIP ({r.status_code}).",
                )

            dest_path.write_bytes(r.content)
            return

    raise HTTPException(
        status_code=400,
        detail=f"Too many redirects (max {MAX_REDIRECTS}) while downloading repo ZIP.",
    )


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


@app.post("/scan", response_model=ScanResponse)
async def scan(
    request: Request,
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
            detail=f"File too large. Maximum upload size is {MAX_UPLOAD_MB}MB.",
        )

    job_id = next(tempfile._get_candidate_names())
    job_dir = WORK_ROOT / job_id
    ensure_dir(job_dir)

    archive_path = job_dir / project.filename
    content = await project.read()
    archive_path.write_bytes(content)

    repo_dir = job_dir / "repo"
    ensure_dir(repo_dir)

    try:
        unzip_to_dir(archive_path, repo_dir)
    except Exception as e:
        safe_rmtree(job_dir)
        raise HTTPException(status_code=400, detail=f"Invalid zip upload: {e}")

    scan_root = _maybe_use_single_top_folder(repo_dir)

    semgrep, osv, gitleaks, entropy, findings = _scan_repo_dir(scan_root)

    try:
        async with await get_db() as db:
            await db.execute(
                "INSERT INTO jobs (job_id, project_name, scan_method) VALUES (?, ?, ?)",
                (job_id, project_name, "zip"),
            )
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
            await db.executemany(
                "INSERT INTO findings (id, job_id, rule_id, severity, category, file_path, line_number, cwe, scanner, message, package_name, package_version) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            await db.commit()
    except Exception:
        logger.exception("DB write failed for job %s", job_id)
    return ScanResponse(
        job_id=job_id,
        project_name=project_name,
        repo_path=str(scan_root),
        findings=findings,
        scanners={
            "semgrep": {"ok": True, "count": len(semgrep)},
            "osv": {"ok": True, "count": len(osv)},
            "gitleaks": {"ok": True, "count": len(gitleaks)},
            "entropy": {"ok": True, "count": len(entropy)},
        },
    )


@app.post("/scan-url", response_model=ScanResponse)
async def scan_url(
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

    semgrep, osv, gitleaks, entropy, findings = _scan_repo_dir(scan_root)

    try:
        db = await get_db()
        try:
            await db.execute(
                "INSERT INTO jobs (job_id, project_name, scan_method) VALUES (?, ?, ?)",
                (job_id, project_name, "url"),
            )
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
            await db.commit()
        finally:
            await db.close()
    except Exception:
        logger.exception("DB write failed for job %s", job_id)

    return ScanResponse(
        job_id=job_id,
        project_name=project_name,
        repo_path=str(scan_root),
        findings=findings,
        scanners={
            "semgrep": {"ok": True, "count": len(semgrep)},
            "osv": {"ok": True, "count": len(osv)},
            "gitleaks": {"ok": True, "count": len(gitleaks)},
            "entropy": {"ok": True, "count": len(entropy)},
        },
    )


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


@app.get("/jobs/{job_id}/findings/csv")
async def get_findings_csv(job_id: str):
    import csv
    import io

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

    output = io.StringIO(newline="")
    # Write UTF-8 BOM for Microsoft Excel compatibility
    output.write("\ufeff")
    writer = csv.writer(output, lineterminator="\r\n")
    
    # Write CSV header row
    writer.writerow([
        "finding_id",
        "scanner",
        "severity",
        "file_path",
        "line_number",
        "title",
        "description",
        "status"
    ])
    
    # Write findings
    for row in rows:
        row_dict = dict(zip(columns, row))
        
        finding_id = row_dict.get("id") or ""
        scanner = row_dict.get("scanner") or ""
        severity = row_dict.get("severity") or ""
        file_path = row_dict.get("file_path") or ""
        line_number = row_dict.get("line_number")
        line_number_str = str(line_number) if line_number is not None else ""
        
        # rule_id acts as title/name
        title = row_dict.get("rule_id") or ""
        description = row_dict.get("message") or ""
        
        # findings are currently hardcoded to "open" on the UI as there's no status storage
        status = "open"
        
        writer.writerow([
            finding_id,
            scanner,
            severity,
            file_path,
            line_number_str,
            title,
            description,
            status
        ])
        
    csv_content = output.getvalue()
    output.close()
    
    headers = {
        "Content-Disposition": f'attachment; filename="findings-{job_id}.csv"',
        "Content-Type": "text/csv"
    }
    return Response(content=csv_content, media_type="text/csv", headers=headers)


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
    github_username: str
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
