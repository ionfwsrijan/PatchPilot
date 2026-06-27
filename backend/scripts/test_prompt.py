import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.ml.llm_patcher import build_patch_prompt


def main():
    sample_finding = {
        "id": "vuln-123",
        "title": "SQL Injection",
        "description": "Unsanitized user input is passed directly into a database execution string.",
        "metadata": {"cwe": "CWE-89"},
        "location": {"path": "src/database/query.py"},
    }

    sample_context = """
def get_user_data(user_id: str):
    db = get_connection()
    query = "SELECT * FROM users WHERE id = '" + user_id + "'"
    result = db.execute(query)
    return result.fetchall()
"""

    prompt = build_patch_prompt(sample_finding, sample_context)

    print("=== GENERATED PROMPT ===")
    print(prompt)
    print("========================")


if __name__ == "__main__":
    main()
