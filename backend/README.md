# PatchPilot Backend

FastAPI backend for PatchPilot.

## Database Schema

SQLite database (`patchpilot.db`) is auto-created in `backend/` on first server startup. The application initializes the following tables to manage scans, findings, fixes, and contributor statistics.

### `org_jobs`
Tracks organization-level scanning job batches.
| Column       | Type | Description                                 |
| ------------ | ---- | ------------------------------------------- |
| `id`         | TEXT | Primary key                                 |
| `org_name`   | TEXT | Name of the organization being scanned      |
| `status`     | TEXT | Current status of the organization job      |
| `created_at` | TEXT | Timestamp of creation (Defaults to `now`)   |

### `jobs`
Tracks individual repository scan jobs.
| Column              | Type    | Description                                                 |
| ------------------- | ------- | ----------------------------------------------------------- |
| `job_id`            | TEXT    | Primary key                                                 |
| `project_name`      | TEXT    | Name of the scanned project                                 |
| `scan_method`       | TEXT    | `zip` or `url`                                              |
| `created_at`        | TEXT    | Timestamp of job creation                                   |
| `org_job_id`        | TEXT    | Links to the parent organization job (references `org_jobs.id`) |
| `status`            | TEXT    | Scan status (Defaults to `completed`)                       |
| `raw_finding_count` | INTEGER | Total findings before deduplication                         |
| `finding_count`     | INTEGER | Final finding count after processing                        |

### `findings`
Stores individual security issues and vulnerabilities detected during a job.
| Column            | Type    | Description                                               |
| ----------------- | ------- | --------------------------------------------------------- |
| `id`              | TEXT    | Primary key                                               |
| `job_id`          | TEXT    | Job ID this finding belongs to (references `jobs.job_id`) |
| `rule_id`         | TEXT    | Rule that triggered the finding                           |
| `severity`        | TEXT    | `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, `INFO`               |
| `category`        | TEXT    | Vulnerability category                                    |
| `file_path`       | TEXT    | File where finding was detected                           |
| `line_number`     | INTEGER | Line number of the finding                                |
| `cwe`             | TEXT    | CWE identifier                                            |
| `scanner`         | TEXT    | `semgrep`, `osv`, or `gitleaks`                           |
| `message`         | TEXT    | Description of the finding                                |
| `package_name`    | TEXT    | Target package name (for dependency findings)             |
| `package_version` | TEXT    | Version of the vulnerable package                         |
| `ml_score`        | REAL    | Machine learning confidence score for prioritization      |
| `false_positive`  | INTEGER | Flag marking the finding as a false positive              |
| `labeled_at`      | TEXT    | Timestamp when the finding was labeled                    |
| `version`         | INTEGER | Finding version tracking (Defaults to 1)                  |
| `created_at`      | TEXT    | Timestamp of finding creation                             |

### `verify_outcomes`
Records the results of the verification pipeline after fixes are applied.
| Column                  | Type    | Description                                               |
| ----------------------- | ------- | --------------------------------------------------------- |
| `id`                    | TEXT    | Primary key                                               |
| `job_id`                | TEXT    | Job ID verified (references `jobs.job_id`)                |
| `passed`                | INTEGER | Boolean indicating if the verification passed             |
| `new_issues_introduced` | INTEGER | Count of new issues caused by the fix                     |
| `verified_at`           | TEXT    | Timestamp of verification                                 |

### `contributor_stats`
Tracks gamification and leaderboard statistics for open-source contributors.
| Column            | Type    | Description                               |
| ----------------- | ------- | ----------------------------------------- |
| `github_username` | TEXT    | Primary key (GitHub handle)               |
| `findings_closed` | INTEGER | Count of security findings resolved       |
| `fixes_passed`    | INTEGER | Count of successful fixes generated       |
| `prs_merged`      | INTEGER | Count of Pull Requests successfully merged|
| `last_updated`    | TEXT    | Timestamp of last stat update             |

### `dependency_links`
Maps project dependencies for calculating the blast radius.
| Column            | Type | Description                                                   |
| ----------------- | ---- | ------------------------------------------------------------- |
| `id`              | TEXT | Primary key                                                   |
| `org_job_id`      | TEXT | Parent organization job ID (references `org_jobs.id`)         |
| `project_name`    | TEXT | Name of the project                                           |
| `package_name`    | TEXT | Name of the dependency package                                |
| `package_version` | TEXT | Version of the dependency                                     |
| `created_at`      | TEXT | Timestamp of link creation                                    |

### `fixes`
Stores proposed remediations and patch diff metrics for findings.
| Column            | Type    | Description                                              |
| ----------------- | ------- | -------------------------------------------------------- |
| `id`              | TEXT | Primary key                                              |
| `job_id`          | TEXT    | Job ID (references `jobs.job_id`)                        |
| `finding_id`      | TEXT    | Target finding being fixed (references `findings.id`)    |
| `diff_line_count` | INTEGER | Number of lines changed in the patch                     |
| `diff_file_count` | INTEGER | Number of files modified by the patch                    |
| `fix_type`        | TEXT    | Type of fix (`insert`, `delete`, `mixed`, or `none`)     |
| `created_at`      | TEXT    | Timestamp of fix creation                                |
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
