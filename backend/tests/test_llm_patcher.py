from app.ml.llm_patcher import _get_language, build_patch_prompt


def test_build_patch_prompt_scanner_finding():
    finding = {
        "description": "Scanner XSS vulnerability",
        "metadata": {"cwe_category": "CWE-79"},
        "location": {"path": "src/components/App.tsx"},
    }
    prompt = build_patch_prompt(finding, "<div>{userInput}</div>")

    assert "Description: Scanner XSS vulnerability" in prompt
    assert "CWE Identifier: CWE-79" in prompt
    assert "File Path: src/components/App.tsx" in prompt
    assert "Programming Language: TypeScript (React)" in prompt


def test_build_patch_prompt_database_finding():
    finding = {
        "message": "Database SQLi vulnerability",
        "cwe": "CWE-89",
        "file_path": "backend/db.py",
    }
    prompt = build_patch_prompt(finding, "SELECT *")

    assert "Description: Database SQLi vulnerability" in prompt
    assert "CWE Identifier: CWE-89" in prompt
    assert "File Path: backend/db.py" in prompt
    assert "Programming Language: Python" in prompt


def test_build_patch_prompt_missing_and_none_data():
    finding = {
        "description": None,
        "message": None,
        "metadata": None,
        "location": None,
        "cwe": None,
        "file_path": None,
    }
    prompt = build_patch_prompt(finding, "some code")

    assert "Description: No description provided." in prompt
    assert "CWE Identifier: Unknown CWE" in prompt
    assert "File Path: unknown_file" in prompt
    assert "Programming Language: Unknown" in prompt


def test_get_language():
    assert _get_language("server.py") == "Python"
    assert _get_language("index.ts") == "TypeScript"
    assert _get_language("Makefile") == "Unknown"
