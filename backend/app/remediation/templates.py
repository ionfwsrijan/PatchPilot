from __future__ import annotations

from typing import List


def secret_remediation_note() -> List[str]:
    return [
        "1) Treat this secret as compromised: rotate/revoke it immediately.",
        "2) Remove it from the repo and history (e.g., git filter-repo/BFG) if it was committed.",
        "3) Add secret scanning in CI and a pre-commit hook (gitleaks) to prevent recurrence.",
        "4) Store secrets in a manager (AWS Secrets Manager, GCP Secret Manager, Vault) and inject via env vars.",
    ]


def dependency_upgrade_note() -> List[str]:
    return [
        "1) Identify the affected package and safe fixed version in the OSV record.",
        "2) Upgrade the dependency (and lockfile) and run full test suite.",
        "3) Re-run OSV-Scanner to confirm the vulnerability is resolved.",
        "4) Add Dependabot/Renovate and CI policy gates for future prevention.",
    ]
