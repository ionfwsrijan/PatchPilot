# Changelog

All notable changes to PatchPilot will be documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/). PatchPilot uses [Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH`.

---

## [Unreleased]

### Added

- **Severity Ranker (Issue #329)**: Introduced deterministic severity ranking (`backend/app/ml/severity_ranker.py`) that normalizes scanner findings to a 0.0–10.0 scale (`severity_score`) using CVSS vectors (v2, v3, v4 via `cvss>=3.0`), Semgrep categories, and secret/entropy metadata.
- **Database Schema Migration**: Added `severity_score REAL DEFAULT 5.0` to `findings` table in SQLite, non-destructively migrated in `init_db()` with `ORDER BY severity_score DESC NULLS LAST, created_at`.
- **Frontend & Architecture Synchronization**: Added `severity_score` to frontend Finding types, mappers, and updated `ARCHITECTURE.md` with scoring hierarchy.

- **Expired job cleanup (Issue #333)**: an hourly background pass removes jobs idle for longer than `JOB_TTL_HOURS` (default `24`, `0` disables, decimals accepted) together with their workspace folder and their `jobs`, `findings`, `verify_outcomes` and `fixes` rows. **On by default**, so existing deployments lose jobs older than 24 hours shortly after upgrading; see the README for the details and the single-process assumption.

### Fixed

- `delete_job()` (and so `DELETE /jobs/{job_id}`) now also deletes the job's rows from `fixes`, which used to be left behind, and it runs all its deletes in one transaction.

---

## [0.1.0] — 2026-05-27

Initial public release.

### Added

- `POST /scan` — upload a ZIP codebase and run security scanners
- `POST /scan-url` — import a GitHub repository URL and scan it server-side
- `POST /fix` — generate proposed remediations for selected findings
- `POST /verify` — run verification checks on a scanned job
- `POST /evidence-pack` — export a ZIP containing audit artifacts and diffs
- `DELETE /jobs/{job_id}` — clean up a job workspace
- `GET /health` — health check endpoint
- Aggregated findings from **Semgrep** (SAST), **OSV-Scanner** (dependency vulnerabilities), and **Gitleaks** (secret detection)
- Simple severity + category sorting on findings
- React + Vite + Tailwind frontend with Dashboard, Findings, and Verify views
- FastAPI backend with async job handling

### Repository

- `README.md` with setup, usage, and API documentation
- `LICENSE` (MIT)
- `CONTRIBUTING.md` with ML roadmap and contributor guide
- `CODE_OF_CONDUCT.md`
- `SECURITY.md` with responsible disclosure policy
- GitHub issue templates (bug report, feature request, ML component)
- GitHub PR template
- CI workflow (backend lint + frontend build)
- Root `.gitignore`

---

[Unreleased]: https://github.com/ionfwsrijan/PatchPilot/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ionfwsrijan/PatchPilot/releases/tag/v0.1.0
