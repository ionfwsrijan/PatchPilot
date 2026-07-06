def _get_language(file_path: str) -> str:
    ext_map = {
        "py": "Python",
        "js": "JavaScript",
        "ts": "TypeScript",
        "tsx": "TypeScript (React)",
        "jsx": "JavaScript (React)",
        "go": "Go",
        "java": "Java",
        "c": "C",
        "cpp": "C++",
        "cs": "C#",
        "rb": "Ruby",
        "php": "PHP",
        "html": "HTML",
        "css": "CSS",
        "json": "JSON",
        "yaml": "YAML",
        "yml": "YAML",
        "sh": "Shell",
        "rs": "Rust",
        "md": "Markdown",
    }
    if "." in file_path:
        ext = file_path.split(".")[-1].lower()
        return ext_map.get(ext, ext.upper())
    return "Unknown"


def build_patch_prompt(finding: dict, code_context: str) -> str:
    description = (
        finding.get("description")
        or finding.get("message")
        or "No description provided."
    )

    metadata = finding.get("metadata") or {}
    cwe = (
        finding.get("cwe")
        or metadata.get("cwe_category")
        or metadata.get("cwe")
        or "Unknown CWE"
    )

    location = finding.get("location") or {}
    file_path = finding.get("file_path") or location.get("path") or "unknown_file"

    language = _get_language(file_path)

    prompt = f"""You are an expert security engineer tasked with patching a vulnerability.

CRITICAL INSTRUCTIONS:
1. You must return ONLY a valid unified diff.
2. DO NOT wrap the output in Markdown code fences (e.g., ```diff or ```python).
3. DO NOT include any natural language explanations, greetings, or commentary before or after the diff.
4. Your output must begin exactly with the string: --- {file_path}

--- VULNERABILITY DETAILS ---
Description: {description}
CWE Identifier: {cwe}
File Path: {file_path}
Programming Language: {language}

--- VULNERABLE SOURCE CODE CONTEXT ---
<context>
{code_context}
</context>

--- EXPECTED OUTPUT FORMAT EXAMPLE ---
--- {file_path}
+++ {file_path}
@@ -10,3 +10,3 @@
-    vulnerable_function_call(user_input)
+    safe_function_call(sanitize(user_input))
"""
    return prompt
