import shutil
import zipfile
from pathlib import Path

from app.utils.fs import unzip_to_dir


def run_test():
    zip_path = Path("evil.zip")
    out_dir = Path("test_extract_dir")
    out_dir.mkdir(parents=True, exist_ok=True)
    print("📦 Forging malicious ZIP file...")
    with zipfile.ZipFile(zip_path, "w") as z:
        z.writestr("../pwned.txt", "You have been hacked!")
    print("🛡️  Testing unzip_to_dir function...\n")
    try:
        unzip_to_dir(zip_path, out_dir)
        print("❌ FAIL: The extraction worked. You are still vulnerable to Zip Slip.")
    except ValueError as e:
        print("✅ SUCCESS: The attack was blocked!")
        print(f"🔒 Exception caught: {e}")
    finally:
        if zip_path.exists():
            zip_path.unlink()
        if out_dir.exists():
            shutil.rmtree(out_dir)


if __name__ == "__main__":
    run_test()
