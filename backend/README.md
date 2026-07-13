# PatchPilot Backend

FastAPI backend for PatchPilot.

## Database Schema

SQLite database (`patchpilot.db`) is auto-created in `backend/` on first server startup.

### `jobs`

| Column         | Type | Description                 |
| -------------- | ---- | --------------------------- |
| `job_id`       | TEXT | Primary key                 |
| `project_name` | TEXT | Name of the scanned project |
| `scan_method`  | TEXT | `zip` or `url`              |
| `created_at`   | TEXT | Timestamp of job creation   |

### `findings`

| Column        | Type    | Description                                               |
| ------------- | ------- | --------------------------------------------------------- |
| `id`          | TEXT    | Primary key                                               |
| `job_id`      | TEXT    | Job ID this finding belongs to (references `jobs.job_id`) |
| `rule_id`     | TEXT    | Rule that triggered the finding                           |
| `severity`    | TEXT    | `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, `INFO`               |
| `category`    | TEXT    | Vulnerability category                                    |
| `file_path`   | TEXT    | File where finding was detected                           |
| `line_number` | INTEGER | Line number of the finding                                |
| `cwe`         | TEXT    | CWE identifier                                            |
| `scanner`     | TEXT    | `semgrep`, `osv`, or `gitleaks`                           |
| `message`     | TEXT    | Description of the finding                                |
| `created_at`  | TEXT    | Timestamp of finding creation                             |

## Authentication

Several endpoints (including `/leaderboard/update` and `/leaderboard`) are protected by API key authentication.

Set the `PATCHPILOT_API_KEY` environment variable before starting the server:

```bash
export PATCHPILOT_API_KEY="your-secret-key"
```

When set, protected endpoints require an `Authorization: Bearer` header:

```bash
curl -X POST http://localhost:8000/leaderboard/update \
  -H "Authorization: Bearer \$PATCHPILOT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"github_username": "user", "pr_description": "Fixes #1", "fixes_passed": 1, "is_pr_merged": true}'
```

Requests without a valid key receive `401 Unauthorized`.

> **Note:** If `PATCHPILOT_API_KEY` is not set, authentication is disabled. This is intended for local development only — always set the env var in production.
