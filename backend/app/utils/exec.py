from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import List


class CmdResult(dict):
    pass


def run_cmd(cmd: List[str], cwd: Path, timeout_s: int = 300) -> CmdResult:
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")

    try:
        p = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout_s,
            env=env,
        )
        return CmdResult(
            cmd=cmd,
            returncode=p.returncode,
            stdout=p.stdout,
            stderr=p.stderr,
            ok=True,
        )
    except OSError as e:
        return CmdResult(
            cmd=cmd,
            returncode=127,
            stdout="",
            stderr=str(e),
            ok=False,
            os_error=getattr(e, "winerror", None),
        )
    except subprocess.TimeoutExpired as e:
        return CmdResult(
            cmd=cmd,
            returncode=124,
            stdout=getattr(e, "stdout", "") or "",
            stderr=f"TimeoutExpired: {e}",
            ok=False,
        )


def run_cmd_sandboxed(
    cmd: List[str],
    cwd: Path,
    timeout_s: int = 300,
    image: str = "node:20-alpine",
    network: bool = False,
) -> CmdResult:
    """
    Run `cmd` inside an ephemeral, non-root, resource-limited Docker
    container instead of directly on the host. Prevents untrusted
    repository code from achieving remote code execution (issue #211).
    """
    docker_cmd = [
        "docker",
        "run",
        "--rm",
        "--user",
        "1000:1000",
        "--memory",
        "512m",
        "--cpus",
        "1",
        "--pids-limit",
        "256",
        "--security-opt",
        "no-new-privileges",
        "--cap-drop",
        "ALL",
        "-v",
        f"{cwd.resolve()}:/workspace",
        "-w",
        "/workspace",
    ]

    if not network:
        docker_cmd += ["--network", "none"]

    docker_cmd += [image, *cmd]

    env = os.environ.copy()

    try:
        p = subprocess.run(
            docker_cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            env=env,
        )
        return CmdResult(
            cmd=cmd,
            returncode=p.returncode,
            stdout=p.stdout,
            stderr=p.stderr,
            ok=True,
            sandboxed=True,
        )
    except OSError as e:
        return CmdResult(
            cmd=cmd,
            returncode=127,
            stdout="",
            stderr=str(e),
            ok=False,
            sandboxed=True,
        )
    except subprocess.TimeoutExpired as e:
        return CmdResult(
            cmd=cmd,
            returncode=124,
            stdout=getattr(e, "stdout", "") or "",
            stderr=f"TimeoutExpired: {e}",
            ok=False,
            sandboxed=True,
        )