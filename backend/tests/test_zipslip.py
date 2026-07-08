import shutil
import zipfile
from pathlib import Path

import pytest

from app.utils.fs import unzip_to_dir


def test_zip_slip_standard():
    zip_path = Path("evil.zip")
    out_dir = Path("test_extract_dir")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    with zipfile.ZipFile(zip_path, "w") as z:
        z.writestr("../pwned.txt", "You have been hacked!")
        
    try:
        with pytest.raises(ValueError, match="Zip Slip blocked"):
            unzip_to_dir(zip_path, out_dir)
    finally:
        if zip_path.exists():
            zip_path.unlink()
        if out_dir.exists():
            shutil.rmtree(out_dir)


def test_zip_slip_symlink():
    zip_path = Path("evil_symlink.zip")
    out_dir = Path("test_extract_dir_symlink")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    with zipfile.ZipFile(zip_path, "w") as z:
        # Create a symlink entry pointing outside the output directory
        info = zipfile.ZipInfo("evil_link")
        info.create_system = 3
        info.external_attr = 0xA1ED0000
        z.writestr(info, "../escaped_dir")
        
        # A file inside the symlink path
        z.writestr("evil_link/passwd", "malicious_content")
        
    try:
        with pytest.raises(ValueError, match="Zip Slip blocked"):
            unzip_to_dir(zip_path, out_dir)
    finally:
        if zip_path.exists():
            zip_path.unlink()
        if out_dir.exists():
            shutil.rmtree(out_dir)


def run_test():
    print("📦 Forging malicious path-traversal ZIP file...")
    try:
        test_zip_slip_standard()
        print("✅ SUCCESS: Standard Zip Slip was blocked!")
    except Exception as e:
        print(f"❌ FAIL: Standard Zip Slip test failed! {e}")
        raise e

    print("📦 Forging malicious symlink ZIP file...")
    try:
        test_zip_slip_symlink()
        print("✅ SUCCESS: Symlink-based Zip Slip was blocked!")
    except Exception as e:
        print(f"❌ FAIL: Symlink-based Zip Slip test failed! {e}")
        raise e


if __name__ == "__main__":
    run_test()

