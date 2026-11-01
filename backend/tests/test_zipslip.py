import shutil
import stat
import zipfile
from pathlib import Path

import pytest

from app.utils.fs import unzip_to_dir


def test_zipslip_traversal(tmp_path: Path):
    zip_path = tmp_path / "evil_traversal.zip"
    out_dir = tmp_path / "extract"
    out_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path, "w") as z:
        z.writestr("../pwned.txt", "You have been hacked!")

    with pytest.raises(ValueError, match="Zip Slip blocked"):
        unzip_to_dir(zip_path, out_dir)


def test_zipslip_symlink_escape_absolute(tmp_path: Path):
    zip_path = tmp_path / "evil_symlink_abs.zip"
    out_dir = tmp_path / "extract"
    out_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path, "w") as z:
        info = zipfile.ZipInfo("evil_link")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        z.writestr(info, "/etc")
        z.writestr("evil_link/passwd", "malicious content")

    with pytest.raises(ValueError, match="Symlink target escapes"):
        unzip_to_dir(zip_path, out_dir)


def test_zipslip_symlink_escape_relative(tmp_path: Path):
    zip_path = tmp_path / "evil_symlink_rel.zip"
    out_dir = tmp_path / "extract"
    out_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path, "w") as z:
        info = zipfile.ZipInfo("evil_link")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        z.writestr(info, "../../escaped")
        z.writestr("evil_link/pwned.txt", "malicious content")

    with pytest.raises(ValueError, match="Symlink target escapes"):
        unzip_to_dir(zip_path, out_dir)


def run_test():
    zip_path = Path("evil.zip")
    out_dir = Path("test_extract_dir")
    out_dir.mkdir(parents=True, exist_ok=True)
    print("Forging malicious ZIP file with path traversal...")
    with zipfile.ZipFile(zip_path, "w") as z:
        z.writestr("../pwned.txt", "You have been hacked!")
    print("Testing unzip_to_dir function...\n")
    try:
        unzip_to_dir(zip_path, out_dir)
        print("FAIL: The extraction worked. You are still vulnerable to Zip Slip.")
    except ValueError as e:
        print("SUCCESS: The attack was blocked!")
        print(f"Exception caught: {e}")
    finally:
        if zip_path.exists():
            zip_path.unlink()
        if out_dir.exists():
            shutil.rmtree(out_dir)

    print("\nForging malicious ZIP file with symlink escape...")
    sym_zip_path = Path("evil_sym.zip")
    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(sym_zip_path, "w") as z:
        info = zipfile.ZipInfo("evil_link")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        z.writestr(info, "/etc")
        z.writestr("evil_link/passwd", "malicious content")
    try:
        unzip_to_dir(sym_zip_path, out_dir)
        print("FAIL: The symlink extraction worked.")
    except ValueError as e:
        print("SUCCESS: The symlink escape was blocked!")
        print(f"Exception caught: {e}")
    finally:
        if sym_zip_path.exists():
            sym_zip_path.unlink()
        if out_dir.exists():
            shutil.rmtree(out_dir)


if __name__ == "__main__":
    run_test()
