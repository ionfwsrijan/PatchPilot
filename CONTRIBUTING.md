# Contributing to PatchPilot

Thanks for your interest in contributing. PatchPilot is actively growing — especially around its [ML roadmap](#ml-roadmap) — and outside contributions are very welcome.

---

## Table of contents

- [Getting started](#getting-started)
- [Project structure](#project-structure)
- [Development setup](#development-setup)
- [How to contribute](#how-to-contribute)
- [Branch & commit conventions](#branch--commit-conventions)
- [ML roadmap](#ml-roadmap)
- [Code style](#code-style)
- [Running tests](#running-tests)
- [Opening a pull request](#opening-a-pull-request)
- [What not to do](#what-not-to-do)

---

## Getting started

1. **Find or create an issue** before writing any code. If you want to work on something, comment on the issue so we know it's being picked up and don't duplicate effort.
2. **Fork** the repo and create your branch from `main`.
3. When your change is ready, open a pull request using the PR template.

If you have a question that isn't covered here, open a [Discussion](https://github.com/ionfwsrijan/PatchPilot/discussions) rather than an issue.

---

## Project structure

```
PatchPilot/
├── backend/               # FastAPI server (Python)
│   ├── app/
│   │   ├── main.py        # API routes
│   │   ├── ml/            # ML models and training logic (growing)
│   │   └── ...
│   ├── scripts/           # Training and utility scripts
│   └── requirements.txt
├── frontend/              # React + Vite + Tailwind UI (TypeScript)
│   └── src/
├── .github/
│   ├── ISSUE_TEMPLATE/
│   └── workflows/         # CI
└── README.md
```

---

## Development setup

### Prerequisites

| Tool | Version |
|---|---|
| Python | 3.10+ |
| Node.js | 18+ |
| semgrep | latest |
| osv-scanner | latest |
| gitleaks | latest |

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-ml.txt # Required for ML features
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend runs at `http://localhost:5173` and talks to the backend at `http://localhost:8000` by default. To override:

```bash
# frontend/.env
VITE_API_BASE_URL=http://localhost:8000
```

---

## How to contribute

### Bug fixes

- Open a bug report issue first (or pick an existing one).
- Reproduce the bug locally before writing a fix.
- Include the fix and a brief explanation of the root cause in the PR description.

### New features

- Open a feature request issue and wait for a maintainer to confirm it fits the roadmap before investing significant time.
- Small self-contained improvements (better error messages, UI polish, docs) can go straight to a PR.

### ML components

ML contributions follow the [ML roadmap](#ml-roadmap). Each tier has dedicated issues — pick one, read the prerequisites carefully, and check that the required data/infra from earlier tiers is already merged.

Key rules for ML PRs:
- **Never commit model files** (`.pkl`, `.pt`, `.onnx`, etc.) — they are gitignored.
- Every model must fail gracefully if the model file is absent. The original non-ML behaviour must be preserved as a fallback.
- Include a training script in `backend/scripts/` with a working `--help` flag.
- Document new API fields in `backend/README.md`.

---

## Branch & commit conventions

**Branch naming**

```
feat/short-description         # new feature
fix/short-description          # bug fix
ml/tier1-severity-ranker       # ML component (include tier)
docs/update-contributing       # documentation only
chore/update-deps              # maintenance
```

**Commit messages** — use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add severity ranker endpoint
fix: handle missing osv-scanner manifest gracefully
docs: add Ollama setup instructions to README
chore: bump fastapi to 0.111.0
ml: add false positive classifier training script
```

Keep the subject line under 72 characters. Add a body if the change needs context.

---

## ML roadmap

Contributions that advance the ML roadmap are especially welcome. The tiers build on each other — earlier tiers must be merged and stable before later ones are started.

| Tier | Focus | Status |
|---|---|---|
| **Tier 1** | Persist findings to SQLite, severity ranker, embedding deduplicator, false positive classifier | 🟡 Open for contributions |
| **Tier 2** | Fix success predictor, pattern clusterer, exploit likelihood scorer | 🔒 Requires Tier 1 |
| **Tier 3** | Local LLM patch generation (Ollama), self-healing verify loop, RL reward signal | 🔒 Requires Tier 2 |

Look for issues labelled `ml` to find work that's ready to pick up.

---

## Code style

### Python (backend)

- Formatter: `ruff format` (or `black` as fallback)
- Linter: `ruff check`
- Type hints on all new functions
- No bare `except:` — always catch a specific exception

```bash
pip install ruff
ruff format backend/
ruff check backend/
```

### TypeScript (frontend)

- Formatter/linter: ESLint + Prettier (configured in `frontend/`)
- No `any` types unless genuinely unavoidable — add a comment explaining why

```bash
cd frontend
npm run lint
npm run format
```

---

## Running tests

```bash
# Backend
cd backend
pytest

# Frontend
cd frontend
npm run test      # if configured
```

If there are no tests for the area you're touching, write some. PRs that add new endpoints or ML models without tests will be asked to add them before merging.

---

## Opening a pull request

1. Fill in the PR template completely — partially filled templates slow down review.
2. Link the issue your PR closes (`Closes #123`).
3. Keep PRs focused — one logical change per PR. Large PRs that mix features and refactors are hard to review and slow to merge.
4. If your PR changes the API response shape, update `backend/README.md`.
5. If your PR adds a dependency, explain why it's needed and why an existing dependency doesn't cover it.

A maintainer will review within a few days. Please be patient — this is a volunteer-maintained project.

---

## What not to do

- **Don't open a PR without a linked issue** — it will be closed and you'll be asked to open an issue first.
- **Don't commit `.env` files, secrets, API keys, or model weights** — these will be rejected and you'll need to rotate any secrets immediately.
- **Don't use paid external APIs** in new features — PatchPilot is intentionally free to run. Use Ollama for LLMs, open datasets for training data.
- **Don't break the non-ML fallback** — any ML feature must degrade gracefully if the model file is missing.
