<div align="center">

# 🛡️ PatchPilot

**Automated code security triage — scan, fix, verify, and export compliance evidence. All local. All free.**

[![CI](https://github.com/ionfwsrijan/PatchPilot/actions/workflows/ci.yml/badge.svg)](https://github.com/ionfwsrijan/PatchPilot/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![Node](https://img.shields.io/badge/node-18%2B-green)](https://nodejs.org/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

</div>

---

PatchPilot lets you upload a codebase (ZIP) or import a GitHub repository URL, run multiple security scanners in one shot, get proposed fixes, verify them, and download a compliance evidence pack — without paying for any external service.

## What it does

| Step | What happens |
|---|---|
| **Scan** | Runs SAST + dependency + secret scanning in parallel |
| **Fix** | Proposes remediations for selected findings |
| **Verify** | Re-runs checks to confirm fixes didn't introduce new issues |
| **Evidence Pack** | Exports a ZIP with audit artifacts and diffs for compliance |

## Scanners

- [Semgrep](https://semgrep.dev/) — static analysis (SAST)
- [OSV-Scanner](https://google.github.io/osv-scanner/) — dependency vulnerabilities
- [Gitleaks](https://github.com/gitleaks/gitleaks) — secret detection

Everything runs locally. No data leaves your machine.

---

## Quickstart

### Prerequisites

**Backend**
- Python 3.10+
- `semgrep`, `osv-scanner`, and `gitleaks` available on `PATH`
   - **semgrep**: `pip install semgrep`.
   - **osv-scanner**: Download from the latest GitHub release and place it in a directory on your `PATH`.
   - **gitleaks**: Install via `brew install gitleaks` (macOS/Linux) or download from the latest GitHub release.

> **Note:** If the backend starts in "degraded mode," it means it cannot find these scanner executables. Ensure they are installed and their locations are included in your system's `PATH` environment variable.


**Frontend**
- Node.js 18+

### 1 — Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-ml.txt # Required for ML features (ranking, deduplication)
uvicorn app.main:app --reload --port 8000
```

### 2 — Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173` in your browser.

### 3 — Run your first scan

1. Go to **Dashboard**
2. Upload a ZIP or paste a GitHub repo URL
3. View findings in the **Findings** tab
4. Go to **Verify** to generate and download an **Evidence Pack**

---

## Configuration

Backend environment variables. `backend/.env.example` lists them with comments (the app reads real environment variables, so export them or pass the file with `docker run --env-file`).

| Variable | Default | Description |
|---|---|---|
| `JOB_TTL_HOURS` | `24` | How long a job may sit idle before the hourly cleanup removes it. `0` turns cleanup off, decimals like `0.5` are fine, and anything that isn't a finite number of 0 or more (`nan`, `inf`, `1e999`, negative numbers, text) logs a warning and falls back to `24`. See "Expired job cleanup" below. |

### Expired job cleanup

**Cleanup is on by default.** Upgrading an existing deployment means jobs that have been idle for more than 24 hours get removed shortly after the app starts (the first pass runs about a minute after startup, then every hour). Set `JOB_TTL_HOURS=0` before upgrading if you want to keep them, or a bigger value to keep them for longer.

- **What is removed:** the job's workspace folder on disk and its rows in `jobs`, `findings`, `verify_outcomes` and `fixes`. Org jobs go once all their repo jobs are gone (with their dependency links). Findings, reports and evidence packs of a removed job are gone too.
- **Which timestamp decides:** a job counts as expired when both its `created_at` and the last activity on its workspace folder are older than the TTL. The folder's modified time is the last activity: it is set when a scan creates the workspace and its output folders, and `/fix`, `/verify` and `/evidence-pack` refresh it when they start and when they finish. So a job you are still working with is not removed just because it was created a day ago. Jobs with no `created_at` are aged by the folder alone, and are removed if the folder is gone.
- **In use right now:** scans that are still running, org batches that are still running, and jobs that a Fix, Verify or evidence pack request is working on are skipped. The evidence pack ZIP is refreshed when it is built, so the TTL counts from that point; a download that takes longer than the whole TTL to stream is not protected.
- **Failures:** each job is removed workspace first, then all its rows in one database transaction. If the workspace can't be fully removed (permissions, a locked file) the error is logged and the job, rows included, stays and is retried on the next pass, so there is no state where the rows are gone but the files are still half there. If the database delete fails after the folder is gone, it is rolled back and the next pass finishes the job.
- **Single process only:** "running" and "in use" are tracked in the API process's memory (`ACTIVE_SCANS` and a small in-use registry), so they are only reliable when the API runs as a single process, which is what the Dockerfile and the uvicorn command above do. With more than one worker (`uvicorn --workers N`, gunicorn) a worker can't see the scans and requests of the others, and the only protection left is the workspace's last-activity time, which does not cover a scan or request that outlives the TTL. In that setup keep a large TTL or set `JOB_TTL_HOURS=0`.
- **Leftover folders:** a folder in the work directory with no `jobs` row is also removed once it is older than the TTL, but only if its name looks like a generated job id (8 characters of `a-z`, `0-9`, `_`) and it contains a `repo` folder, and it is not a symlink. Other folders in a shared `PATCHPILOT_WORKDIR` are never touched, but point `PATCHPILOT_WORKDIR` at a folder of its own if you can.

---

## API reference

| Method | Route | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `POST` | `/scan` | Upload ZIP and scan |
| `POST` | `/scan-url` | Import GitHub repo URL and scan |
| `POST` | `/fix` | Generate proposed fixes |
| `POST` | `/verify` | Verify fixes |
| `POST` | `/evidence-pack` | Build and download evidence ZIP |
| `DELETE` | `/jobs/{job_id}` | Delete a job workspace |

**`POST /scan`** — FormData: `project` (file), `project_name` (optional)

**`POST /scan-url`** — FormData: `repo_url`, `ref` (optional, default `main`), `project_name` (optional)

**`POST /fix`** — JSON: `{ "job_id": "...", "finding_ids": ["..."] }`

---

## ML roadmap

PatchPilot is being transformed from a rule-based scanner into an intelligent, self-improving security platform — layer by layer. All models use free, locally-running tools (no API keys).

| Tier | Focus | Status |
|---|---|---|
| **Tier 1 — Triage** | Persist findings to SQLite · Severity ranker · Embedding deduplicator · False positive classifier | 🟢 Completed |
| **Tier 2 — Predictive** | Fix success predictor · Pattern clusterer · Exploit likelihood scorer | 🟢 Completed |
| **Tier 3 — Autonomous** | Local LLM patch generation (Ollama) · Self-healing verify loop · RL reward signal | 🟢 Completed |

Each tier feeds training data into the next. See [CONTRIBUTING.md](CONTRIBUTING.md#ml-roadmap) for how to pick up a Tier 1 issue.

---

## Repository structure

```
PatchPilot/
├── backend/               # FastAPI server (Python)
│   ├── app/
│   │   ├── main.py        # API routes
│   │   └── ml/            # ML models (Tier 1+ contributions go here)
│   ├── scripts/           # Training and utility scripts
│   └── requirements.txt
├── frontend/              # React + Vite + Tailwind (TypeScript)
│   └── src/
├── .github/
│   ├── ISSUE_TEMPLATE/    # Bug, feature, and ML issue templates
│   └── workflows/         # CI (backend lint + frontend build)
├── CONTRIBUTING.md
├── SECURITY.md
├── CHANGELOG.md
└── LICENSE
```

## Architecture

Want to understand how the internal components communicate? Check out the [ARCHITECTURE.md](ARCHITECTURE.md) document for Mermaid diagrams and details on the Scan, Fix, and Verify pipelines, database schema, and ML roadmap flow.

---

## Contributing

Contributions are welcome — especially ML components advancing the roadmap above.

Read [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions, branch conventions, code style, and the ML contribution guide.

For questions and ideas, open a [Discussion](https://github.com/ionfwsrijan/PatchPilot/discussions) rather than an issue.

## Mentors

Special thanks to the mentors helping guide contributors and review changes.

- <img src="https://github.com/ionfwsrijan.png?size=40" width="40" height="40" alt="@ionfwsrijan"/> @ionfwsrijan
- <img src="https://github.com/arpit2006.png?size=40" width="40" height="40" alt="@arpit2006"/> @arpit2006


## Contributors

Thanks to all our contributors ❤️

<a href="https://github.com/ionfwsrijan/PatchPilot/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=ionfwsrijan/PatchPilot" />
</a>

---

## Security

Found a vulnerability in PatchPilot itself? Please **do not** open a public issue. Read [SECURITY.md](SECURITY.md) for the responsible disclosure process.

---

## License

MIT — see [LICENSE](LICENSE).
