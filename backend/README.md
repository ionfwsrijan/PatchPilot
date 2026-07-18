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

## API Reference

| Method | Route | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `GET` | `/jobs` | List scan jobs (paginated) |
| `GET` | `/jobs/{job_id}/findings` | Get findings for a specific job |
| `DELETE` | `/jobs/{job_id}` | Delete a job workspace |
| `POST` | `/scan` | Upload ZIP and scan |
| `POST` | `/scan-url` | Import GitHub repo URL and scan |
| `POST` | `/fix` | Generate proposed fixes |
| `POST` | `/verify` | Verify fixes |
| `POST` | `/evidence-pack` | Build and download evidence ZIP |
