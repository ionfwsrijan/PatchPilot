from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..models import VerifyResponse
from ..utils.exec import run_cmd


def _find_npm_command() -> Optional[str]:
    for name in ("npm.cmd", "npm.exe", "npm"):
        p = shutil.which(name)
        if p:
            return p
    try:
        out = subprocess.check_output(
            ["where.exe", "npm"], text=True, stderr=subprocess.STDOUT
        )
        first = (out.strip().splitlines() or [None])[0]
        return first
    except Exception:
        return None


def _has_node_modules(repo_dir: Path) -> bool:
    return (repo_dir / "node_modules").exists()


def _read_package_json(repo_dir: Path) -> Dict[str, Any]:
    pj = repo_dir / "package.json"
    return json.loads(pj.read_text(encoding="utf-8"))


def _pick_verification_script(scripts: Dict[str, Any]) -> Optional[List[str]]:
    """
    Return npm args for a good verification command.
    Prefer: test -> lint -> build
    """
    if "test" in scripts:
        return ["test"]
    if "lint" in scripts:
        return ["run", "lint"]
    if "build" in scripts:
        return ["run", "build"]
    return None


def verify_repo(repo_dir: Path) -> VerifyResponse:
    checks: Dict[str, Any] = {}

    if (repo_dir / "package.json").exists():
        npm_path = _find_npm_command()
        if not npm_path:
            checks["npm"] = {
                "ok": False,
                "reason": "npm not found on PATH for backend process",
            }
            return VerifyResponse(ok=False, checks=checks)

        if not _has_node_modules(repo_dir):
            has_lock = (repo_dir / "package-lock.json").exists() or (
                repo_dir / "npm-shrinkwrap.json"
            ).exists()
            if has_lock:
                r_ci = run_cmd([npm_path, "ci"], cwd=repo_dir, timeout_s=1200)
                checks["npm_ci"] = r_ci
                if r_ci.get("returncode") != 0:
                    return VerifyResponse(ok=False, checks=checks)
            else:
                r_i = run_cmd([npm_path, "install"], cwd=repo_dir, timeout_s=1200)
                checks["npm_install"] = r_i
                if r_i.get("returncode") != 0:
                    return VerifyResponse(ok=False, checks=checks)

        try:
            pkg = _read_package_json(repo_dir)
        except Exception as e:
            checks["package_json"] = {
                "ok": False,
                "reason": f"Failed to read package.json: {e}",
            }
            return VerifyResponse(ok=False, checks=checks)

        scripts = pkg.get("scripts") or {}
        chosen = _pick_verification_script(scripts)

        if not chosen:
            checks["npm_verify"] = {
                "ok": True,
                "skipped": True,
                "reason": "No test/lint/build script found in package.json scripts; skipping Node verification.",
                "available_scripts": sorted(list(scripts.keys())),
            }
            return VerifyResponse(ok=True, checks=checks)

        r = run_cmd([npm_path, *chosen], cwd=repo_dir, timeout_s=1200)
        checks["npm_verify"] = {
            "selected": chosen,
            "available_scripts": sorted(list(scripts.keys())),
        }
        checks["npm_run"] = r
        ok = r.get("returncode") == 0
        return VerifyResponse(ok=ok, checks=checks)

    if (repo_dir / "pyproject.toml").exists() or (
        repo_dir / "requirements.txt"
    ).exists():
        if shutil.which("pytest") is None:
            checks["pytest"] = {
                "ok": True,
                "skipped": True,
                "reason": "pytest not found; skipping",
            }
            return VerifyResponse(ok=True, checks=checks)

        r = run_cmd(["pytest", "-q"], cwd=repo_dir, timeout_s=600)
        checks["pytest"] = r
        ok = r.get("returncode") == 0
        return VerifyResponse(ok=ok, checks=checks)

    r = run_cmd(
        ["python", "-c", "print('verify: no tests detected')"],
        cwd=repo_dir,
        timeout_s=30,
    )
    checks["fallback"] = r
    return VerifyResponse(ok=True, checks=checks)
