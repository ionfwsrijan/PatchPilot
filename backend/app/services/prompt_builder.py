import os

class PromptBuilder:
    @staticmethod
    def build_patch_prompt(finding_meta: dict, file_path: str, source_code: str) -> str:
        """
        Builds a prompt to generate a unified diff for a given finding and source code context.
        """
        ext = os.path.splitext(file_path)[1].lower() if file_path else ""
        language = "code"
        if ext in [".py"]:
            language = "python"
        elif ext in [".js", ".jsx"]:
            language = "javascript"
        elif ext in [".ts", ".tsx"]:
            language = "typescript"
        elif ext in [".go"]:
            language = "go"
        elif ext in [".java"]:
            language = "java"
        elif ext in [".c", ".cpp", ".h", ".hpp"]:
            language = "c/c++"

        title = finding_meta.get("title", "Unknown Vulnerability")
        severity = finding_meta.get("severity", "UNKNOWN")
        description = finding_meta.get("description", "")
        rule_id = finding_meta.get("rule_id", "unknown-rule")

        prompt = f"""You are an expert security engineer and developer.
Your task is to fix a security vulnerability in the provided {language} code.

VULNERABILITY DETAILS:
- Title: {title}
- Rule ID: {rule_id}
- Severity: {severity}
- Description: {description}

FILE:
{file_path}

SOURCE CODE CONTEXT:
```{language}
{source_code}
```

INSTRUCTIONS:
1. Analyze the vulnerability and the surrounding source code.
2. Provide a patch that fixes the vulnerability without breaking existing functionality.
3. Your output MUST be a valid unified diff (diff -u format) that can be applied directly to the file.
4. Do NOT wrap the diff in markdown code blocks. The diff should start with `---` and `+++`.
5. Only output the diff, no explanations or additional text.

DIFF:
"""
        return prompt
