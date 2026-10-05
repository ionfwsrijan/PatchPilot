> **Before opening:** make sure there is an issue tracking this work, and link it below. PRs without a linked issue may be closed without review.

## Linked issue

Closes #38

## What this PR does

Adds a SQLite persistence layer for scan findings. Previously, findings were stored only in memory and were lost after server restarts. This PR introduces SQLite integration, a findings schema, CRUD helper functions, and persistent storage keyed by `job_id`.

## Type of change

- [ ] Bug fix
- [x] New feature
- [ ] ML model / training pipeline
- [ ] Refactor (no behaviour change)
- [ ] Documentation
- [ ] Tests only

## ML tier (if applicable)

- [ ] Tier 1 — Triage
- [ ] Tier 2 — Predictive
- [ ] Tier 3 — Autonomous
- [x] Not ML-related

## Stack affected

- [x] Backend
- [ ] Frontend
- [ ] Both

---

## Changes

### Backend

- Integrated SQLite database.
- Added schema for storing scan findings.
- Implemented CRUD helper functions.
- Persisted findings using `job_id`.
- Stored scanner type, severity, title and timestamps.

### Frontend

- No frontend changes.

### New dependencies

- SQLite driver.

### Database / schema changes

- Added SQLite schema for persistent scan findings storage.

---

## Testing

**How did you test this?**

- Ran the application locally.
- Executed a scan.
- Verified findings were written to SQLite.
- Retrieved findings using `job_id`.
- Restarted the server and confirmed findings persisted.

**Checklist**

- [x] Tested locally end-to-end (upload ZIP or GitHub URL → scan → findings returned correctly)
- [ ] New ML model falls back gracefully when model file is absent
- [x] No new `console.error` or unhandled Python exceptions introduced
- [ ] Added or updated tests where applicable
- [x] `requirements.txt` / `package.json` updated if new dependencies added
- [ ] New model files (`.pkl`, `.pt`, etc.) are gitignored, not committed

---

## Anything reviewers should focus on

Please review the SQLite schema, CRUD implementation, and integration with the scan workflow to ensure findings are persisted and retrieved correctly.

## Screenshots (if UI changed)

N/A (Backend-only changes)
