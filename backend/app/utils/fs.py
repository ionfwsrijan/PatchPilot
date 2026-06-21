from __future__ import annotations

import os
import re
import shutil
import zipfile
from pathlib import Path


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def safe_rmtree(p: Path) -> None:
    shutil.rmtree(p, ignore_errors=True)


def unzip_to_dir(zip_path: Path, out_dir: Path) -> None:
    out_path = out_dir.resolve()
    with zipfile.ZipFile(zip_path, "r") as z:
        for member_name in z.namelist():
            member_path = (out_path / member_name).resolve()
            if out_path not in member_path.parents and member_path != out_path:
                raise ValueError(
                    f"Zip Slip blocked: malicious file path detected '{member_name}'"
                )

        z.extractall(out_dir)

    children = list(out_dir.iterdir())
    if len(children) == 1 and children[0].is_dir():
        top = children[0]
        tmp = out_dir.parent / (out_dir.name + "_tmp")
        tmp.mkdir(parents=True, exist_ok=True)
        for item in top.iterdir():
            shutil.move(str(item), str(tmp / item.name))
        shutil.rmtree(top)
        for item in tmp.iterdir():
            shutil.move(str(item), str(out_dir / item.name))
        shutil.rmtree(tmp)


def check_reachability(
    repo_dir: Path, package_names: set[str]
) -> dict[str, tuple[bool, str | None]]:
    ignore_dirs = {
        ".git",
        "node_modules",
        "venv",
        ".venv",
        "env",
        "__pycache__",
        "dist",
        "build",
        ".next",
    }
    target_exts = {".js", ".jsx", ".ts", ".tsx", ".py", ".cjs", ".mjs"}

    results = {pkg: (False, None) for pkg in package_names}
    remaining = set(package_names)

    compiled_patterns = {}
    for pkg in package_names:
        patterns = [
            rf"require\s*\(\s*['\"]{re.escape(pkg)}(?:/[^'\"]+)?['\"]\s*\)",
            rf"from\s+['\"]{re.escape(pkg)}(?:/[^'\"]+)?['\"]",
            rf"import\s+['\"]{re.escape(pkg)}(?:/[^'\"]+)?['\"]",
            rf"import\s+{re.escape(pkg)}\b",
            rf"from\s+{re.escape(pkg)}\b\s+import",
        ]
        compiled_patterns[pkg] = [re.compile(p) for p in patterns]

    for root, dirs, files in os.walk(repo_dir):
        dirs[:] = [d for d in dirs if d not in ignore_dirs]

        if not remaining:
            break

        for file in files:
            path = Path(root) / file
            if path.suffix not in target_exts:
                continue

            try:
                with open(path, "r", encoding="utf-8") as f:
                    for line_num, line in enumerate(f, 1):
                        found = []
                        for pkg in remaining:
                            for pattern in compiled_patterns[pkg]:
                                if pattern.search(line):
                                    rel_path = path.relative_to(repo_dir)
                                    results[pkg] = (
                                        True,
                                        f"Imported in {rel_path}: line {line_num}",
                                    )
                                    found.append(pkg)
                                    break
                        for pkg in found:
                            remaining.remove(pkg)
                        if not remaining:
                            break
            except (UnicodeDecodeError, PermissionError, OSError):
                continue

            if not remaining:
                break

    return results
