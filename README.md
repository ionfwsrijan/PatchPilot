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
| **Tier 1 — Triage** | Persist findings to SQLite · Severity ranker · Embedding deduplicator · False positive classifier | 🟡 Open for contributions |
| **Tier 2 — Predictive** | Fix success predictor · Pattern clusterer · Exploit likelihood scorer | 🔒 Requires Tier 1 |
| **Tier 3 — Autonomous** | Local LLM patch generation (Ollama) · Self-healing verify loop · RL reward signal | 🔒 Requires Tier 2 |

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
