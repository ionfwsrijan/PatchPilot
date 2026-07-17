# Changelog

All notable changes to PatchPilot will be documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/). PatchPilot uses [Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH`.

---

## [Unreleased]

_Changes on `main` that haven't been tagged yet will appear here._

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
