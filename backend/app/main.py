from __future__ import annotations

import asyncio
import functools
import json
import logging
import os
import random
import re
import shutil
import tempfile
import threading
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import List

import aiosqlite
import httpx
from fastapi import (
    BackgroundTasks,
    Depends,
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

from .db import (
    create_findings,
    create_job,
    delete_job,
    get_cwe_distribution,
    get_db,
    get_dependency_diff,
    get_finding,
    get_findings_by_job_id,
    get_job,
    get_leaderboard_stats,
    get_trend_data,
    init_db,
    update_finding_status,
    update_job_status,
    upsert_contributor_stat,
)
from .ml.deduplicator import SENTENCE_TRANSFORMERS_AVAILABLE, deduplicate
from .ml.fp_predictor import predictor
from .ml.ranker import load_ranker, scoring_function
from .models import (
    Finding,
    FindingStatusUpdate,
    Fix,
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
from .security import verify_api_key
from .utils.fs import ensure_dir, safe_job_dir, safe_rmtree, unzip_to_dir

try:
    import tomllib
except ImportError:  # Python 3.10
    import tomli as tomllib  # type: ignore[no-redef]

_MAX_UPLOAD_MB_RAW = os.environ.get("MAX_UPLOAD_MB")
RANKER = load_ranker()

try:
    MAX_UPLOAD_MB = int(_MAX_UPLOAD_MB_RAW) if _MAX_UPLOAD_MB_RAW else 100
except ValueError:
    MAX_UPLOAD_MB = 100

MAX_UPLOAD_MB = max(1, MAX_UPLOAD_MB)
MAX_UPLOAD_SIZE = MAX_UPLOAD_MB * 1024 * 1024

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    # Start background cleanup for finished ACTIVE_SCANS entries
    asyncio.create_task(_cleanup_active_scans_loop())
    yield


app = FastAPI(title="PatchPilot API", version="0.1.0", lifespan=lifespan)

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


@app.get("/api/health/ollama", tags=["Health"])
async def ollama_health():
    """
    Ping the local Ollama service to verify availability and list installed models.
    Fails gracefully to prevent 500 errors if the service is down.
    """
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    timeout = httpx.Timeout(3.0)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(f"{base_url}/api/tags")

            if response.status_code == 200:
                data = response.json()
                models = [model.get("name") for model in data.get("models", [])]
                return {
                    "available": True,
                    "models": models,
                    "base_url": base_url,
                }
            else:
                return {
                    "available": False,
                    "models": [],
                    "base_url": base_url,
                }
    except (httpx.RequestError, ValueError, AttributeError, TypeError) as e:
        logger.warning(f"Ollama health check failed: {e}")
        return {
            "available": False,
            "models": [],
            "base_url": base_url,
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
    Currently supports package.json (Node), requirements.txt and
    pyproject.toml (Python — Poetry and PEP 621).
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

    pyproject_path = repo_dir / "pyproject.toml"
    if pyproject_path.exists():
        try:
            with pyproject_path.open("rb") as f:
                data = tomllib.load(f)

            # Projects using Poetry as a PEP 621 build backend can declare
            # both sections; track names so each package is added only once.
            pyproject_seen = set()

            poetry_deps = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
            for name, spec in poetry_deps.items():
                if name == "python":
                    continue
                if isinstance(spec, str):
                    version = spec
                elif isinstance(spec, dict):
                    version = str(spec.get("version", "unknown"))
                else:
                    version = "unknown"
                pyproject_seen.add(name.lower())
                deps.append((name, version))

            for req in data.get("project", {}).get("dependencies", []):
                # Drop environment markers ("pkg>=1.0; python_version<'3.11'")
                # and allow extras ("pkg[extra]>=1.0").
                req = str(req).split(";")[0].strip()
                match = re.match(
                    r"^([a-zA-Z0-9._\-]+)(?:\[[^\]]*\])?\s*(?:[=<>~!]+\s*(.*))?$", req
                )
                if match:
                    name = match.group(1)
                    if name.lower() in pyproject_seen:
                        continue
                    pyproject_seen.add(name.lower())
                    version = (match.group(2) or "unknown").strip()
                    deps.append((name, version))
        except Exception as e:
            logger.warning("Failed to parse pyproject.toml in %s: %s", repo_dir, e)

    return deps


ACTIVE_SCANS: dict[str, dict] = {}
ORG_CANCEL_EVENTS = {}

# How long to keep completed/failed scan progress in memory for SSE clients.
# After this TTL, entries are removed to prevent unbounded growth.
_ACTIVE_SCANS_RETENTION_SECONDS_RAW = os.environ.get("ACTIVE_SCANS_RETENTION_SECONDS")
try:
    ACTIVE_SCANS_RETENTION_SECONDS = (
        int(_ACTIVE_SCANS_RETENTION_SECONDS_RAW)
        if _ACTIVE_SCANS_RETENTION_SECONDS_RAW
        else 600
    )
except ValueError:
    ACTIVE_SCANS_RETENTION_SECONDS = 600

ACTIVE_SCANS_RETENTION_SECONDS = max(1, ACTIVE_SCANS_RETENTION_SECONDS)


def _scan_repo_dir(
    repo_dir: Path,
    progress_cb=None,
    job_dir: Path = None,
    cancel_event: threading.Event = None,
    raw_dir_name: str = "raw",
):
    if cancel_event and cancel_event.is_set():
        raise asyncio.CancelledError()
    if progress_cb:
        progress_cb("sast", "in_progress")

    semgrep_raw_out = (job_dir / raw_dir_name / "semgrep.json") if job_dir else None
    semgrep = run_semgrep(repo_dir, raw_out=semgrep_raw_out)

    if cancel_event and cancel_event.is_set():
        raise asyncio.CancelledError()

    if progress_cb:
        progress_cb("sast", "completed")

    if progress_cb:
        progress_cb("dependency", "in_progress")

    osv_raw_out = (job_dir / raw_dir_name / "osv.json") if job_dir else None
    osv = run_osv_scanner(repo_dir, raw_out=osv_raw_out)

    if cancel_event and cancel_event.is_set():
        raise asyncio.CancelledError()

    if progress_cb:
        progress_cb("dependency", "completed")

    if progress_cb:
        progress_cb("secrets", "in_progress")

    gitleaks_raw_out = (job_dir / raw_dir_name / "gitleaks.json") if job_dir else None
    gitleaks = run_gitleaks(repo_dir, raw_out=gitleaks_raw_out)

    if cancel_event and cancel_event.is_set():
        raise asyncio.CancelledError()

    if progress_cb:
        progress_cb("secrets", "completed")

    findings = []
    findings.extend(semgrep)
    findings.extend(osv)
    entropy = run_entropy(repo_dir)

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


async def _cleanup_active_scans_loop() -> None:
    """Periodically remove finished scan entries from ACTIVE_SCANS.

    This prevents unbounded memory growth in long-running deployments.
    """
    while True:
        try:
            cutoff = (
                datetime.now(timezone.utc).timestamp() - ACTIVE_SCANS_RETENTION_SECONDS
            )
            # Copy keys to avoid mutating while iterating.
            for job_id in list(ACTIVE_SCANS.keys()):
                state = ACTIVE_SCANS.get(job_id)
                if not state:
                    continue
                status = state.get("status")
                if status not in {"completed", "failed", "aborted"}:
                    continue

                finished_at = state.get("finished_at")
                if finished_at is None:
                    # If finished_at is missing, keep entry for safety.
                    continue

                if finished_at <= cutoff:
                    ACTIVE_SCANS.pop(job_id, None)
        except Exception:
            logger.exception("ACTIVE_SCANS cleanup loop error")
        await asyncio.sleep(30)


def finding_key(f: Finding):
    """Generate a stable identifier for a finding.
    Uses rule identifier, file path, and start line so that findings from the
    same rule on different lines are treated as distinct findings.
    """
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


async def download_to_path(
    url: str,
    dest_path: Path,
    max_retries: int = 5,
    cancel_event: threading.Event = None,
) -> None:
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

                        try:
                            with open(dest_path, "wb") as f:
                                async for chunk in r.aiter_bytes(chunk_size=chunk_size):
                                    bytes_received += len(chunk)
                                    if bytes_received > MAX_UPLOAD_SIZE:
                                        raise HTTPException(
                                            status_code=413,
                                            detail=f"Remote repository exceeds the maximum limit of {MAX_UPLOAD_MB}MB.",
                                        )
                                    f.write(chunk)
                        except Exception:
                            try:
                                if dest_path.exists():
                                    dest_path.unlink()
                            except Exception:
                                pass
                            raise
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


async def _apply_fp_predictor(findings: List[Finding]) -> None:
    ml_input = []
    for f in findings:
        rule_id = (
            (f.metadata or {}).get("check_id")
            or (f.metadata or {}).get("rule")
            or (f.metadata or {}).get("osv_id")
            or f.title
        )
        ml_input.append(
            {
                "rule_id": rule_id,
                "message": f.description or f.title,
                "file_path": f.location.path if f.location else "",
                "ml_score": getattr(f, "ml_score", 1.0),
            }
        )

    adjusted_scores = await run_in_threadpool(predictor.adjust_scores, ml_input)

    for f, new_score in zip(findings, adjusted_scores):
        f.ml_score = new_score


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
            await create_job(db, job_id, project_name, scan_method)
        finally:
            await db.close()

        job_dir = safe_job_dir(WORK_ROOT, job_id)
        semgrep, osv, gitleaks, entropy, findings = await run_in_threadpool(
            functools.partial(
                _scan_repo_dir, scan_root, update_progress, job_dir=job_dir
            )
        )

        raw_finding_count = len(findings)

        disable_dedup = os.environ.get("DISABLE_DEDUP", "").lower() == "true"
        try:
            epsilon = float(os.environ.get("DEDUP_EPSILON", 0.15))
        except ValueError:
            epsilon = 0.15

        if not disable_dedup and SENTENCE_TRANSFORMERS_AVAILABLE:
            findings = deduplicate(findings, epsilon)

        await _apply_fp_predictor(findings)

        finding_count = len(findings)

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
                        f.title,
                        f.severity,
                        f.category,
                        file_path,
                        line_number,
                        None,
                        scanner,
                        message,
                        pkg_name,
                        pkg_version,
                        f.ml_score,
                        json.dumps(f.features) if f.features else None,
                    )
                )
            if rows:
                await create_findings(db, rows)
            await update_job_status(
                db, job_id, "completed", raw_finding_count, finding_count
            )
        finally:
            await db.close()

        if job_id in ACTIVE_SCANS:
            ACTIVE_SCANS[job_id]["status"] = "completed"
            ACTIVE_SCANS[job_id]["findings_count"] = finding_count
            ACTIVE_SCANS[job_id]["finished_at"] = datetime.now(timezone.utc).timestamp()

    except Exception:
        logger.exception("Failed scan task for %s", job_id)
        if job_id in ACTIVE_SCANS:
            ACTIVE_SCANS[job_id]["status"] = "failed"
            ACTIVE_SCANS[job_id]["finished_at"] = datetime.now(timezone.utc).timestamp()

        try:
            db = await get_db()
            try:
                await update_job_status(db, job_id, "failed")
            finally:
                await db.close()
        except Exception:
            logger.exception("Failed to write failed status for job %s", job_id)


@app.post(
    "/scan",
    summary="Scan an uploaded project archive",
    description=(
        "Uploads a ZIP archive containing a project, extracts it, "
        "and starts an asynchronous security scan. "
        "The endpoint immediately returns a job ID that can be used "
        "to monitor scan progress and retrieve results."
    ),
    response_model=dict,
    responses={
        400: {"description": "Invalid ZIP archive or upload error."},
        413: {"description": "Uploaded file exceeds the maximum allowed size."},
        500: {"description": "Internal server error."},
    },
)
async def scan(
    request: Request,
    background_tasks: BackgroundTasks,
    project: UploadFile = File(
        ...,
        description="ZIP archive containing the project source code to scan.",
    ),
    project_name: str = Form(
        "project",
        description="Display name assigned to the uploaded project.",
    ),
):
    """
    Upload a project archive and start an asynchronous security scan.

    The uploaded ZIP file is extracted into a temporary workspace,
    validated, and queued for background scanning. The endpoint
    returns immediately with a unique job ID that can be used to
    track scan progress and retrieve scan results.
    """
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


@app.post(
    "/scan-url",
    summary="Scan a GitHub repository",
    description=(
        "Downloads a GitHub repository as a ZIP archive using the "
        "specified repository URL and branch, then starts an "
        "asynchronous security scan. Returns a job ID for tracking "
        "the scan progress and results."
    ),
    responses={
        400: {"description": "Invalid repository URL or repository download failed."},
        404: {"description": "Repository or branch not found."},
        429: {"description": "GitHub API rate limit exceeded."},
        500: {"description": "Internal server error."},
    },
)
async def scan_url(
    background_tasks: BackgroundTasks,
    repo_url: str = Form(
        ...,
        description="Public GitHub repository URL to scan.",
    ),
    ref: str = Form(
        "main",
        description="Git branch to download and scan.",
    ),
    project_name: str = Form(
        "project",
        description="Display name assigned to this scan.",
    ),
):
    """
    Download a GitHub repository and start an asynchronous security scan.

    The repository is downloaded as a ZIP archive, extracted into a
    temporary workspace, and queued for background scanning. A job ID
    is returned immediately for tracking scan progress and retrieving
    results.
    """
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


async def _record_fixes_to_db(job_id: str, fixes: List[Fix]):
    try:
        db = await get_db()
        try:
            rows = []
            for f in fixes:
                if not f.diff:
                    continue
                diff_str = f.diff
                adds = 0
                dels = 0
                for line in diff_str.split("\n"):
                    if line.startswith("+") and not line.startswith("+++"):
                        adds += 1
                    elif line.startswith("-") and not line.startswith("---"):
                        dels += 1

                diff_line_count = adds + dels
                files = f.files_changed
                diff_file_count = len(files) if files else 0

                if adds == 0 and dels == 0:
                    fix_type = "none"
                elif adds > 0 and dels == 0:
                    fix_type = "insert"
                elif dels > 0 and adds == 0:
                    fix_type = "delete"
                else:
                    fix_type = "mixed"

                rows.append(
                    (
                        str(uuid.uuid4()),
                        job_id,
                        f.finding_id,
                        diff_line_count,
                        diff_file_count,
                        fix_type,
                    )
                )
            if rows:
                await db.executemany(
                    "INSERT INTO fixes "
                    "(id, job_id, finding_id, diff_line_count, "
                    "diff_file_count, fix_type) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    rows,
                )
                await db.commit()
        finally:
            await db.close()
    except Exception:
        logger.exception("Failed to record fixes to DB for job %s", job_id)


@app.post(
    "/fix",
    response_model=FixResponse,
    summary="Generate remediation suggestions",
    description=(
        "Generates automated fix suggestions for one or more selected "
        "security findings within a previously scanned project. "
        "The generated fixes are returned to the client and recorded "
        "asynchronously for reporting purposes."
    ),
    responses={
        404: {"description": "Specified scan job was not found."},
        422: {"description": "Invalid request payload."},
        500: {"description": "Internal server error."},
    },
)
def fix(req: FixRequest, background_tasks: BackgroundTasks):
    """
    Generate remediation suggestions for selected findings.

    Uses the specified job ID and finding IDs to produce proposed
    fixes for detected security issues. Generated fixes are returned
    immediately and stored asynchronously for later reporting.
    """
    try:
        job_dir = safe_job_dir(WORK_ROOT, req.job_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    repo_dir = job_dir / "repo"
    if not repo_dir.exists():
        raise HTTPException(status_code=404, detail="Unknown job_id")

    repo_dir = _maybe_use_single_top_folder(repo_dir)
    fixes = propose_fixes(repo_dir, req.finding_ids)

    background_tasks.add_task(_record_fixes_to_db, req.job_id, fixes)

    return FixResponse(job_id=req.job_id, fixes=fixes)


async def get_baseline_findings(job_id: str):
    db = await get_db()
    try:
        cursor = await db.execute(
            """
            SELECT rule_id, file_path
            FROM findings
            WHERE job_id = ?
            """,
            (job_id,),
        )
        rows = await cursor.fetchall()

        return {(row[0], row[1]) for row in rows}
    finally:
        await db.close()


@app.post(
    "/verify",
    response_model=VerifyResponse,
    summary="Verify repository fixes",
    description=(
        "Verifies whether the applied fixes successfully resolve the "
        "detected security issues. The repository is rescanned and "
        "compared against the baseline scan to identify any newly "
        "introduced issues."
    ),
    responses={
        404: {"description": "Specified scan job was not found."},
        422: {"description": "Invalid request parameters."},
        500: {"description": "Internal server error."},
    },
)
async def verify(
    job_id: str = Form(
        ...,
        description="Identifier of the scan job to verify.",
    ),
    baseline_job_id: str | None = Form(
        None,
        description=(
            "Optional baseline scan job ID used for comparison. "
            "If omitted, the current job is used as the baseline."
        ),
    ),
):
    """
    Verify that applied fixes resolve previously detected security issues.

    The repository is rescanned and compared with a baseline scan to
    determine whether fixes were successful and whether any new
    vulnerabilities were introduced.
    """
    try:
        job_dir = safe_job_dir(WORK_ROOT, job_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    repo_dir = job_dir / "repo"
    if not repo_dir.exists():
        raise HTTPException(status_code=404, detail="Unknown job_id")

    repo_dir = _maybe_use_single_top_folder(repo_dir)

    result = await run_in_threadpool(verify_repo, repo_dir)

    if baseline_job_id is not None:
        try:
            safe_job_dir(WORK_ROOT, baseline_job_id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    baseline_job_id = baseline_job_id or job_id
    baseline_findings = await get_baseline_findings(baseline_job_id)

    _, _, _, _, findings = await run_in_threadpool(
        functools.partial(
            _scan_repo_dir,
            repo_dir,
            job_dir=job_dir,
            raw_dir_name="raw_verify",
        )
    )

    current_findings = {finding_key(f) for f in findings}

    new_findings = current_findings - baseline_findings

    new_issues_introduced = len(new_findings)
    logger.info(
        "Verify detected %d new findings for job %s",
        new_issues_introduced,
        job_id,
    )

    passed = 1 if result.ok and new_issues_introduced == 0 else 0

    verify_dir = job_dir / "raw_verify"
    verify_dir.mkdir(parents=True, exist_ok=True)
    verify_report = {
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "passed": bool(passed),
        "new_issues_introduced": new_issues_introduced,
        "baseline_job_id": baseline_job_id,
    }
    await run_in_threadpool(
        (verify_dir / "verification-report.json").write_text,
        json.dumps(verify_report, indent=2),
        encoding="utf-8",
    )

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


@app.post(
    "/evidence-pack",
    summary="Generate an evidence package",
    description=(
        "Generates a downloadable evidence package containing scan "
        "artifacts, reports, and supporting files for a completed "
        "security scan. Optionally refreshes the raw scan outputs "
        "before creating the evidence package."
    ),
    responses={
        200: {"description": "Evidence package generated successfully."},
        404: {"description": "Specified scan job was not found."},
        422: {"description": "Invalid request parameters."},
        500: {"description": "Internal server error."},
    },
)
def evidence_pack(
    job_id: str = Form(
        ...,
        description="Identifier of the scan job for which the evidence package should be generated.",
    ),
    project_name: str = Form(
        "project",
        description="Display name of the project included in the generated reports.",
    ),
    update_raw: bool = Form(
        False,
        description="If true, refreshes the raw scan results before generating the evidence package.",
    ),
):
    """
    Generate a downloadable evidence package for a completed scan.

    The evidence package includes reports, raw scanner outputs, and
    supporting artifacts that can be used for auditing, compliance,
    or sharing scan results.
    """
    try:
        job_dir = safe_job_dir(WORK_ROOT, job_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    repo_dir = job_dir / "repo"
    if not repo_dir.exists():
        raise HTTPException(status_code=404, detail="Unknown job_id")

    repo_dir = _maybe_use_single_top_folder(repo_dir)

    if update_raw:
        verify_dir = job_dir / "raw_verify"
        if verify_dir.exists():
            _scan_repo_dir(repo_dir, job_dir=job_dir, raw_dir_name="raw_verify")
        else:
            _scan_repo_dir(repo_dir, job_dir=job_dir, raw_dir_name="raw")

    out_dir = job_dir / "out"
    ensure_dir(out_dir)

    pack_path = build_evidence_pack(
        repo_dir=repo_dir,
        out_dir=out_dir,
        project_name=project_name,
        job_id=job_id,
        job_dir=job_dir,
    )
    return FileResponse(
        path=str(pack_path), filename=pack_path.name, media_type="application/zip"
    )


@app.get(
    "/api/scans/{job_id}/report/pdf",
    tags=["Reports"],
    dependencies=[Depends(verify_api_key)],
)
async def download_audit_pdf(job_id: str):
    db = await get_db()
    try:
        job_row = await get_job(db, job_id)
        if job_row is None:
            raise HTTPException(
                status_code=404, detail=f"No job found with id '{job_id}'"
            )

        project_name = job_row["project_name"]
        rows = await get_findings_by_job_id(db, job_id)
    finally:
        await db.close()

    findings_list = []
    for row in rows:
        loc = None
        if row["file_path"]:
            loc = Location(path=row["file_path"], start_line=row["line_number"])

        findings_list.append(
            Finding(
                id=row["id"],
                title=row.get("title") or row.get("rule_id") or "Unknown",
                severity=row.get("severity") or "INFO",
                category=row.get("category") or "Unknown",
                location=loc,
                description=row.get("message") or "",
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


@app.get(
    "/jobs/{job_id}/findings",
    dependencies=[Depends(verify_api_key)],
)
async def get_findings(job_id: str):
    db = await get_db()
    try:
        job_row = await get_job(db, job_id)
        if job_row is None:
            raise HTTPException(
                status_code=404, detail=f"No job found with id '{job_id}'"
            )

        raw_finding_count = job_row.get("raw_finding_count")
        finding_count = job_row.get("finding_count")

        findings = await get_findings_by_job_id(db, job_id)
    finally:
        await db.close()

    if raw_finding_count is None:
        raw_finding_count = len(findings)
    if finding_count is None:
        finding_count = len(findings)

    return {
        "job_id": job_id,
        "raw_finding_count": raw_finding_count,
        "finding_count": finding_count,
        "findings": findings,
    }


class LabelFindingRequest(BaseModel):
    false_positive: bool
    expected_version: int


@app.post("/findings/{finding_id}/label")
async def label_finding(finding_id: str, payload: LabelFindingRequest):
    fp_int = 1 if payload.false_positive else 0

    db = await get_db()
    try:
        cursor = await db.execute(
            """
            UPDATE findings
            SET false_positive = ?, labeled_at = datetime('now'), version = version + 1
            WHERE id = ? AND version = ?
            """,
            (fp_int, finding_id, payload.expected_version),
        )

        if cursor.rowcount == 0:
            # Distinguish between a missing finding (404) and a stale version (409)
            cur2 = await db.execute(
                "SELECT id FROM findings WHERE id = ?", (finding_id,)
            )
            if not await cur2.fetchone():
                raise HTTPException(status_code=404, detail="Finding not found")
            raise HTTPException(
                status_code=409,
                detail="Finding has been modified by another user.",
            )

        await db.commit()
    finally:
        await db.close()

    return {
        "status": "success",
        "finding_id": finding_id,
        "false_positive": payload.false_positive,
    }


@app.patch("/findings/{finding_id}/status")
async def update_finding_status_endpoint(finding_id: str, payload: FindingStatusUpdate):
    if payload.status not in ("open", "accepted", "ignored"):
        raise HTTPException(
            status_code=400,
            detail="Invalid status value. Must be 'open', 'accepted', or 'ignored'.",
        )

    db = await get_db()
    try:
        finding = await get_finding(db, finding_id)
        if not finding:
            raise HTTPException(
                status_code=404, detail=f"Finding '{finding_id}' not found."
            )
        await update_finding_status(db, finding_id, payload.status)
    finally:
        await db.close()

    return {"id": finding_id, "status": payload.status}


@app.get(
    "/jobs/{job_id}/verify",
    dependencies=[Depends(verify_api_key)],
)
async def get_verify(job_id: str):
    db = await get_db()
    try:
        job_row = await get_job(db, job_id)
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
async def delete_job_endpoint(job_id: str):
    try:
        job_dir = safe_job_dir(WORK_ROOT, job_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="Job not found")

    safe_rmtree(job_dir)

    db = await get_db()
    try:
        await delete_job(db, job_id)
    finally:
        await db.close()

    return {"deleted": True}


@app.get(
    "/trends",
    dependencies=[Depends(verify_api_key)],
)
async def get_trends_endpoint(limit: int = 6):
    """Fetches historical trend data for the frontend dashboard."""
    data = await get_trend_data(limit)
    return data


@app.get(
    "/cwe-distribution",
    dependencies=[Depends(verify_api_key)],
)
async def cwe_distribution_endpoint():
    """Fetches the vulnerability distribution for the frontend donut chart."""
    data = await get_cwe_distribution()
    return data


@app.get(
    "/dependency-diff",
    dependencies=[Depends(verify_api_key)],
)
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


@app.get(
    "/leaderboard",
    dependencies=[Depends(verify_api_key)],
)
async def leaderboard_endpoint():
    data = await get_leaderboard_stats()
    return data


@app.post(
    "/leaderboard/update",
    dependencies=[Depends(verify_api_key)],
)
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
    cancel_event: threading.Event = None,
):
    async with sem:
        try:
            if cancel_event and cancel_event.is_set():
                raise asyncio.CancelledError()
            db = await get_db()
            try:
                db.row_factory = aiosqlite.Row
                cur = await db.execute(
                    "SELECT status FROM org_jobs WHERE id = ?", (org_job_id,)
                )
                org_row = await cur.fetchone()

                if org_row and org_row["status"] == "aborted":
                    await update_job_status(db, job_id, "aborted")
                    return

                await update_job_status(db, job_id, "scanning")
            finally:
                await db.close()

            job_dir = safe_job_dir(WORK_ROOT, job_id)
            ensure_dir(job_dir)
            archive_path = job_dir / "repo.zip"
            repo_dir = job_dir / "repo"
            ensure_dir(repo_dir)

            zip_url = github_zip_url(repo_url, ref=ref)
            await download_to_path(zip_url, archive_path, cancel_event=cancel_event)
            if cancel_event and cancel_event.is_set():
                raise asyncio.CancelledError()

            unzip_to_dir(archive_path, repo_dir)
            if cancel_event and cancel_event.is_set():
                raise asyncio.CancelledError()

            scan_root = _maybe_use_single_top_folder(repo_dir)
            semgrep, osv, gitleaks, entropy, findings = await run_in_threadpool(
                functools.partial(
                    _scan_repo_dir,
                    scan_root,
                    job_dir=job_dir,
                    cancel_event=cancel_event,
                )
            )

            raw_finding_count = len(findings)

            disable_dedup = os.environ.get("DISABLE_DEDUP", "").lower() == "true"
            try:
                epsilon = float(os.environ.get("DEDUP_EPSILON", 0.15))
            except ValueError:
                epsilon = 0.15

            # CORRECT WAY:
            if not disable_dedup and SENTENCE_TRANSFORMERS_AVAILABLE:
    # The assertion must be safely inside the block body
              assert all(isinstance(f, Finding) for f in findings), \
              f"Expected Finding objects, got {set(type(f).__name__ for f in findings)}"
        
            findings = deduplicate(findings, epsilon)

            await _apply_fp_predictor(findings)

            finding_count = len(findings)

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
                            f.title,
                            f.severity,
                            f.category,
                            file_path,
                            line_number,
                            None,
                            scanner,
                            message,
                            pkg_name,
                            pkg_version,
                            f.ml_score,
                            json.dumps(f.features) if f.features else None,
                        )
                    )

                if rows:
                    await create_findings(db, rows)

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

                await update_job_status(
                    db, job_id, "completed", raw_finding_count, finding_count
                )
            finally:
                await db.close()
        except asyncio.CancelledError:
            logger.info("Scan task %s was aborted", job_id)
            # No database write here
        except Exception:
            logger.exception("Failed repo scan task for job %s", job_id)
            db = await get_db()
            try:
                await update_job_status(db, job_id, "failed")
            finally:
                await db.close()


async def _run_org_batch(org_job_id: str, repos: List[dict]):
    cancel_event = threading.Event()
    ORG_CANCEL_EVENTS[org_job_id] = cancel_event

    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT status FROM org_jobs WHERE id = ?", (org_job_id,)
        )
        row = await cur.fetchone()
        if row and row[0] == "aborted":
            ORG_CANCEL_EVENTS.pop(org_job_id, None)
            return

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
            await create_job(
                db, job_id, project_name, "org_batch", org_job_id, "pending"
            )
        finally:
            await db.close()

        tasks.append(
            asyncio.create_task(
                _run_repo_scan_task(
                    sem, job_id, repo_url, ref, project_name, org_job_id, cancel_event
                )
            )
        )

    cancel_task = asyncio.create_task(asyncio.to_thread(cancel_event.wait))
    wait_tasks = asyncio.create_task(asyncio.gather(*tasks, return_exceptions=True))

    try:
        done, pending = await asyncio.wait(
            [wait_tasks, cancel_task], return_when=asyncio.FIRST_COMPLETED
        )

        if cancel_task in done:
            for t in tasks:
                if not t.done():
                    t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

            db = await get_db()
            try:
                await db.execute(
                    "UPDATE jobs SET status = 'aborted' WHERE org_job_id = ? AND status NOT IN ('completed', 'failed')",
                    (org_job_id,),
                )
                await db.commit()
            finally:
                await db.close()
        else:
            cancel_task.cancel()
    finally:
        cancel_task.cancel()
        ORG_CANCEL_EVENTS.pop(org_job_id, None)

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


@app.post(
    "/api/scans/org",
    dependencies=[Depends(verify_api_key)],
)
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


@app.get(
    "/api/scans/org/{org_job_id}/status",
    response_model=OrgJobStatusResponse,
    dependencies=[Depends(verify_api_key)],
)
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
    if org_job_id in ORG_CANCEL_EVENTS:
        ORG_CANCEL_EVENTS[org_job_id].set()

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
            if org_row["status"] in ["completed", "failed", "aborted"]:
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
                f.cwe,
                f.ml_score
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
