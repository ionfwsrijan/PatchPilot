<div align="center">

# 🛡️ PatchPilot

### Automated code security triage — scan, fix, verify, and export compliance evidence. All local. All free.##

[![CI](https://github.com/ionfwsrijan/PatchPilot/actions/workflows/ci.yml/badge.svg)](https://github.com/ionfwsrijan/PatchPilot/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![Node](https://img.shields.io/badge/node-18%2B-green)](https://nodejs.org/)
[![PRs Welcome](https://img.shields.io/badge/PRs-Welcome-brightgreen.svg)](CONTRIBUTING.md)

</div>

---

PatchPilot lets you **upload a codebase (ZIP) or import a GitHub repository URL, run multiple security scanners in one shot, get proposed fixes, verify them, and download a compliance evidence pack — without paying for any external service.**

## 🚀 What It Does

| Step | What Happens |
|---|---|
| **Scan** | Runs SAST + dependency + secret scanning in parallel |
| **Fix** | Proposes remediations for selected findings |
| **Verify** | Re-runs checks to confirm fixes didn't introduce new issues |
| **Evidence Pack** | Exports a ZIP with audit artifacts and diffs for compliance |

---

## 🔍 Scanners

- [Semgrep](https://semgrep.dev/) — static analysis (SAST)
- [OSV-Scanner](https://google.github.io/osv-scanner/) — dependency vulnerabilities
- [Gitleaks](https://github.com/gitleaks/gitleaks) — secret detection

Everything runs locally. No data leaves your machine.

---

## 🛠️ Tech Stack

| Category | Stack |
|---|---|
| **Backend** | ![Python](https://img.shields.io/badge/Python-3776AB?style=flat&logo=python&logoColor=white) ![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat&logo=fastapi) |
| **Frontend** | ![React](https://img.shields.io/badge/React-20232A?style=flat&logo=react&logoColor=61DAFB) ![Vite](https://img.shields.io/badge/Vite-646CFF?style=flat&logo=vite&logoColor=white) ![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?style=flat&logo=typescript&logoColor=white) ![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-06B6D4?style=flat&logo=tailwindcss&logoColor=white) |
| **Database** | ![SQLite](https://img.shields.io/badge/SQLite-003B57?style=flat&logo=sqlite&logoColor=white) |
| **ML** | ![Scikit-learn](https://img.shields.io/badge/scikit--learn-F7931E?style=flat&logo=scikit-learn&logoColor=white) |

---

## ⚡ Quickstart

### Prerequisites

**Backend**
- Python 3.10+
- `semgrep`, `osv-scanner`, and `gitleaks` available on `PATH`

**Frontend**
- Node.js 18+

### 1 — Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
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

## 🔌 API Reference

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

## 🧠 ML Roadmap

PatchPilot is being transformed from a rule-based scanner into an intelligent, self-improving security platform — layer by layer. All models use free, locally-running tools (no API keys).

| Tier | Focus | Status |
|---|---|---|
| **Tier 1 — Triage** | Persist findings to SQLite · Severity ranker · Embedding deduplicator · False positive classifier | 🟡 Open for contributions |
| **Tier 2 — Predictive** | Fix success predictor · Pattern clusterer · Exploit likelihood scorer | 🔒 Requires Tier 1 |
| **Tier 3 — Autonomous** | Local LLM patch generation (Ollama) · Self-healing verify loop · RL reward signal | 🔒 Requires Tier 2 |

Each tier feeds training data into the next. See [CONTRIBUTING.md](CONTRIBUTING.md#ml-roadmap) for how to pick up a Tier 1 issue.

---

## 📂 Repository structure

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

---

## 🤝 Contributing

Contributions are welcome — especially ML components advancing the roadmap above.

Read [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions, branch conventions, code style, and the ML contribution guide.

For questions and ideas, open a [Discussion](https://github.com/ionfwsrijan/PatchPilot/discussions) rather than an issue.

---

## 🔒 Security

Found a vulnerability in PatchPilot itself? Please **do not** open a public issue. Read [SECURITY.md](SECURITY.md) for the responsible disclosure process.

---

## 📄 License

MIT — see [LICENSE](LICENSE).
